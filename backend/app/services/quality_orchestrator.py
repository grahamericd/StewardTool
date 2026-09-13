from datetime import datetime, timezone
import hashlib
import json
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..integrations.testgen.client import MockTestGenClient, TestGenClient, TestGenError
from ..models import (
    DataAsset, QualityDecision, QualityEngineResource, QualityIssue,
    QualityProfile, QualityResult, QualityRule, StewardshipTask,
)


def now():
    return datetime.now(timezone.utc)


def get_link(db: Session, resource_id: int):
    return db.scalar(select(QualityEngineResource).where(QualityEngineResource.resource_id == resource_id, QualityEngineResource.provider == 'TESTGEN'))


def _apply_testgen_defaults(link: QualityEngineResource):
    """Fill blank mappings from environment defaults without overwriting a resource-specific mapping."""
    if not link.project_code and settings.testgen_project_code:
        link.project_code = settings.testgen_project_code
    if not link.table_group_id and settings.testgen_table_group_id:
        link.table_group_id = settings.testgen_table_group_id
    if not link.test_suite_id and settings.testgen_test_suite_id:
        link.test_suite_id = settings.testgen_test_suite_id
    return link


def _source_mapping_from_link(link: QualityEngineResource):
    cfg = dict(link.configuration or {})
    return {
        "connection_name": cfg.get("source_connection_name"),
        "database": cfg.get("source_database"),
        "schema": cfg.get("source_schema"),
        "table": cfg.get("source_table"),
        "qualified_name": cfg.get("source_qualified_name") or link.external_table_name,
    }


def ensure_link(db: Session, *, organization_id: int, resource_id: int, payload=None):
    link = get_link(db, resource_id)
    if not link:
        link = QualityEngineResource(
            organization_id=organization_id,
            resource_id=resource_id,
            provider='TESTGEN',
        )
        db.add(link)

    _apply_testgen_defaults(link)

    if payload is not None:
        for field in ('project_code','connection_id','table_group_id','test_suite_id','external_table_name'):
            value = getattr(payload, field, None)
            if value not in (None, ""):
                setattr(link, field, value)

        cfg = dict(link.configuration or {})
        for field in ('source_connection_name','source_database','source_schema','source_table'):
            value = getattr(payload, field, None)
            if value is not None:
                cfg[field] = value.strip() if isinstance(value, str) else value

        schema_name = cfg.get("source_schema")
        table_name = cfg.get("source_table")
        if table_name:
            qualified = f"{schema_name}.{table_name}" if schema_name else table_name
            cfg["source_qualified_name"] = qualified
            link.external_table_name = qualified

        link.configuration = cfg or None

    link.sync_status = 'CONFIGURED' if settings.testgen_mode == 'real' else 'MOCK_READY'
    db.flush()
    return link


def _open_task_for_issue(db: Session, issue: QualityIssue):
    existing = db.scalar(select(StewardshipTask).where(
        StewardshipTask.asset_id == issue.asset_id,
        StewardshipTask.source_type == 'QUALITY_ISSUE',
        StewardshipTask.source_reference == str(issue.id),
        StewardshipTask.status == 'OPEN',
    ))
    if existing:
        return existing
    task = StewardshipTask(
        organization_id=issue.organization_id,
        asset_id=issue.asset_id,
        task_type='quality_issue',
        governance_domain='QUALITY',
        title=issue.title,
        why_it_matters=issue.description or 'A quality finding needs a human stewardship decision.',
        recommended_action='Review the evidence and decide whether this is bad data, a valid exception, an expectation that needs to change, or something that needs expert review.',
        priority='HIGH' if issue.severity == 'HIGH' else 'MEDIUM',
        source_type='QUALITY_ISSUE',
        source_reference=str(issue.id),
    )
    db.add(task); db.flush(); return task


def _items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _recursive_number(payload, keys):
    """Find the first numeric value for any candidate key in nested JSON."""
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        for value in payload.values():
            found = _recursive_number(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _recursive_number(value, keys)
            if found is not None:
                return found
    return None


def _normalize_percent(value):
    if value is None:
        return None
    value = float(value)
    if 0 <= value <= 1:
        value *= 100
    return round(max(0.0, min(100.0, value)), 1)


def _result_status(item):
    raw = (
        item.get("status")
        or item.get("result_status")
        or item.get("test_status")
        or item.get("outcome")
        or item.get("result")
    )
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("name") or raw.get("status")
    return str(raw or "").upper()


def _is_failure(item):
    status = _result_status(item)
    return status in {
        "FAIL", "FAILED", "FAILURE", "ERROR",
        "WARNING", "WARN"
    }


def _test_name(item, index):
    for key in (
        "test_name", "test_definition_name", "name",
        "test_suite_name", "description"
    ):
        value = item.get(key)
        if value:
            return str(value)
    return f"TestGen quality check {index}"


def _failed_count(item):
    value = _recursive_number(
        item,
        (
            "failed_count", "failure_count", "failed_rows",
            "failed_row_count", "records_failed",
            "failing_rows", "fail_count",
        ),
    )
    return int(value) if value is not None else None


def _evaluated_count(item):
    value = _recursive_number(
        item,
        (
            "evaluated_count", "record_count", "records_tested",
            "tested_count", "row_count", "total_count",
        ),
    )
    return int(value) if value is not None else None



def _complete_issue_tasks(db: Session, issue_id: int):
    tasks = db.scalars(
        select(StewardshipTask).where(
            StewardshipTask.source_type == "QUALITY_ISSUE",
            StewardshipTask.source_reference == str(issue_id),
            StewardshipTask.status == "OPEN",
        )
    ).all()
    for task in tasks:
        task.status = "COMPLETED"
        task.completed_at = now()


def _reopen_issue_task(db: Session, issue: QualityIssue):
    task = db.scalar(
        select(StewardshipTask).where(
            StewardshipTask.source_type == "QUALITY_ISSUE",
            StewardshipTask.source_reference == str(issue.id),
        )
    )
    if task:
        task.title = issue.title
        task.why_it_matters = issue.description or (
            "A quality finding needs a human stewardship decision."
        )
        task.priority = "HIGH" if issue.severity == "HIGH" else "MEDIUM"
        task.status = "OPEN"
        task.completed_at = None
        return task
    return _open_task_for_issue(db, issue)


def _resolve_issue(db: Session, issue: QualityIssue, *, reason: str | None = None):
    if issue.status != "RESOLVED":
        issue.status = "RESOLVED"
        issue.resolved_at = now()
    details = dict(issue.details or {})
    if reason:
        details["resolution_reason"] = reason
    issue.details = details
    _complete_issue_tasks(db, issue.id)


def _normalize_string(value):
    return " ".join(str(value or "").strip().lower().split())


def _issue_key(issue: QualityIssue):
    details = issue.details or {}
    fingerprint = details.get("fingerprint")
    if fingerprint:
        return str(fingerprint)
    if issue.external_issue_id:
        return f"external:{issue.external_issue_id}"
    return f"title:{_normalize_string(issue.title)}"


def _test_result_key(item, index):
    external_id = (
        item.get("test_definition_id")
        or item.get("test_id")
        or item.get("id")
    )
    if external_id:
        return f"external:{external_id}"
    return f"name:{_normalize_string(_test_name(item, index))}"


def _recursive_strings(payload, keys):
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys:
                if isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, (str, int, float)) or entry is None:
                            found.append(entry)
                elif isinstance(value, (str, int, float)) or value is None:
                    found.append(value)
            if isinstance(value, (dict, list)):
                found.extend(_recursive_strings(value, keys))
    elif isinstance(payload, list):
        for value in payload:
            found.extend(_recursive_strings(value, keys))
    return found


def _evidence_from_test_result(item, index):
    failed_count = _failed_count(item)
    evaluated_count = _evaluated_count(item)

    score = _normalize_percent(
        _recursive_number(
            item,
            (
                "score", "dq_score", "quality_score",
                "pass_rate", "success_rate",
            ),
        )
    )

    samples = _recursive_strings(
        item,
        {
            "sample_values", "failed_values", "example_values",
            "examples", "sample", "value",
        },
    )
    # De-duplicate while preserving order and cap evidence shown to stewards.
    deduped_samples = []
    seen = set()
    for value in samples:
        marker = repr(value)
        if marker not in seen:
            seen.add(marker)
            deduped_samples.append(value)
        if len(deduped_samples) >= 8:
            break

    columns = _recursive_strings(
        item,
        {
            "column", "column_name", "columns",
            "tested_column", "field_name",
        },
    )
    columns = [str(x) for x in columns if x not in (None, "")]
    columns = list(dict.fromkeys(columns))[:8]

    test_type = None
    for key in ("test_type", "test_definition_type", "type", "test_type_name"):
        value = item.get(key)
        if value:
            test_type = str(value)
            break

    message = None
    for key in ("message", "description", "error_message", "result_message"):
        value = item.get(key)
        if value and isinstance(value, str):
            message = value
            break

    return {
        "check_name": _test_name(item, index),
        "status": _result_status(item),
        "test_type": test_type,
        "columns": columns,
        "failed_count": failed_count,
        "evaluated_count": evaluated_count,
        "score": score,
        "sample_values": deduped_samples,
        "message": message,
    }


def _quality_score_from_results(items):
    """
    Prefer row-based pass evidence, then explicit per-check scores,
    then test pass rate. This keeps the displayed score stable and
    explainable across TestGen result shapes.
    """
    evaluated_total = 0
    failed_total = 0
    row_evidence_count = 0
    explicit_scores = []

    for item in items:
        evaluated = _evaluated_count(item)
        failed = _failed_count(item)
        if evaluated is not None and evaluated > 0 and failed is not None:
            evaluated_total += evaluated
            failed_total += max(0, failed)
            row_evidence_count += 1

        score = _normalize_percent(
            _recursive_number(
                item,
                (
                    "score", "dq_score", "quality_score",
                    "pass_rate", "success_rate",
                ),
            )
        )
        if score is not None:
            explicit_scores.append(score)

    if row_evidence_count and evaluated_total > 0:
        return round(
            max(0.0, min(100.0, (1 - failed_total / evaluated_total) * 100)),
            1,
        )

    if explicit_scores:
        return round(sum(explicit_scores) / len(explicit_scores), 1)

    if items:
        passed = sum(1 for item in items if not _is_failure(item))
        return round((passed / len(items)) * 100, 1)

    return 0.0



def _recursive_values(payload, keys):
    values = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value not in (None, "", [], {}):
                values.append(value)
            if isinstance(value, (dict, list)):
                values.extend(_recursive_values(value, keys))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(_recursive_values(value, keys))
    return values


def _first_recursive_value(payload, keys, default=None):
    values = _recursive_values(payload, set(keys))
    return values[0] if values else default


def _display_column(raw):
    value = _first_recursive_value(
        raw,
        (
            "column_name", "column", "field_name", "field",
            "attribute_name", "attribute", "name",
        ),
    )
    if isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("column_name")
            or value.get("column")
        )
    return str(value).strip() if value not in (None, "") else "This field"


def _hygiene_kind(raw):
    # TestGen 5.92.1 exposes the human-readable name in issue_type_name and
    # the numeric code in issue_type. Always prefer the readable value.
    value = _first_recursive_value(
        raw,
        (
            "issue_type_name", "issue_name", "hygiene_type",
            "hygiene_issue_type", "hygiene_issue", "issue",
            "rule_name", "test_name", "type", "category",
            "issue_type",
        ),
        "profiling finding",
    )
    if isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("value")
            or value.get("type")
            or "profiling finding"
        )
    return str(value).strip()


def _parse_testgen_detail(detail):
    """
    Parse TestGen 5.92.1 hygiene detail strings such as:
      Dummy Values: 0, Empty String: 5034, Null: 0, Records: 5195
      Non-Alpha Values: 37, Semantic Type: City, Records: 5195
      Patterns: NNNNN (5064), NNNN (7), Dummy Values: 0
      Minimum Value: 04282026
    """
    if not detail or not isinstance(detail, str):
        return {}

    parsed = {"raw_detail": detail}

    def integer(label):
        match = re.search(
            rf"{re.escape(label)}\s*:\s*([0-9,]+)",
            detail,
            re.IGNORECASE,
        )
        return int(match.group(1).replace(",", "")) if match else None

    for key, label in [
        ("records", "Records"),
        ("empty_string_count", "Empty String"),
        ("null_count", "Null"),
        ("dummy_value_count", "Dummy Values"),
        ("non_alpha_count", "Non-Alpha Values"),
    ]:
        value = integer(label)
        if value is not None:
            parsed[key] = value

    semantic = re.search(
        r"Semantic Type\s*:\s*([^,]+)",
        detail,
        re.IGNORECASE,
    )
    if semantic:
        parsed["semantic_type"] = semantic.group(1).strip()

    minimum = re.search(
        r"Minimum Value\s*:\s*([^,]+)",
        detail,
        re.IGNORECASE,
    )
    if minimum:
        parsed["minimum_value"] = minimum.group(1).strip()

    patterns = re.search(
        r"Patterns\s*:\s*(.*?)(?:,\s*Dummy Values\s*:|$)",
        detail,
        re.IGNORECASE,
    )
    if patterns:
        parsed_patterns = []
        for value, count in re.findall(
            r"([^,]+?)\s*\(([0-9,]+)\)",
            patterns.group(1),
        ):
            parsed_patterns.append(
                {
                    "pattern": value.strip(),
                    "count": int(count.replace(",", "")),
                }
            )
        if parsed_patterns:
            parsed["patterns"] = parsed_patterns

    return parsed


def _hygiene_count(raw):
    value = _first_recursive_value(
        raw,
        (
            "affected_count", "failed_count", "row_count", "record_count",
            "records_affected", "count", "issue_count", "occurrence_count",
        ),
    )
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass

    detail = _first_recursive_value(raw, ("detail", "details"))
    parsed = _parse_testgen_detail(detail)

    # Pick the count that actually describes the hygiene condition.
    issue_name = str(raw.get("issue_type_name") or "").lower()
    if "blank" in issue_name:
        return (
            parsed.get("empty_string_count", 0)
            + parsed.get("null_count", 0)
            + parsed.get("dummy_value_count", 0)
        )
    if "non-alpha" in issue_name:
        return parsed.get("non_alpha_count")
    if "zip code format" in issue_name and parsed.get("patterns"):
        # Sum patterns that are not the canonical NNNNN or NNNNN-NNNN forms.
        bad = 0
        for item in parsed["patterns"]:
            if item["pattern"] not in {"NNNNN", "NNNNN-NNNN"}:
                bad += item["count"]
        return bad

    return None


def _hygiene_examples(raw):
    values = _recursive_values(
        raw,
        {
            "sample_values", "example_values", "examples",
            "sample", "values", "value",
        },
    )
    flattened = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(value)
        elif isinstance(value, (str, int, float)) or value is None:
            flattened.append(value)

    result = []
    seen = set()
    for value in flattened:
        marker = repr(value)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
        if len(result) >= 6:
            break
    return result


def _hygiene_plain_language(column, kind):
    text = kind.lower()
    column_label = column if column != "This field" else "This field"

    patterns = [
        (
            ("non-standard blank values",),
            f"{column_label} contains blanks that are represented inconsistently",
            "Blank values represented as empty strings or other placeholders can behave differently from true null values in validation, matching, and reporting.",
            "Confirm whether blank values are expected for this field. If they are, decide on one standard representation; if they are not, investigate why the source is leaving the field blank.",
            "COMPLETENESS",
        ),
        (
            ("invalid usa zip code format",),
            f"{column_label} contains ZIP codes in unexpected formats",
            "Non-standard ZIP formats can reduce address matching, validation, and interoperability with other systems.",
            "Review the reported format distribution and confirm which formats the business accepts. Standardize or correct invalid formats where appropriate.",
            "CONFORMANCE",
        ),
        (
            ("non-alpha name or address",),
            f"{column_label} contains values that do not match the detected name/address pattern",
            "This may represent legitimate addresses with numbers or punctuation, or it may mean the semantic type was inferred incorrectly.",
            "Review the aggregate evidence and confirm whether the field's detected meaning is correct before treating these values as errors.",
            "CONFORMANCE",
        ),
        (
            ("non-alpha prefixed name",),
            f"{column_label} begins with values that do not match the detected name pattern",
            "This often means the field's inferred semantic meaning does not match the actual business content.",
            "Confirm what this field represents. If it is not actually a name field, adjust the expectation rather than correcting valid data.",
            "SEMANTIC",
        ),
        (
            ("null", "missing", "blank", "empty"),
            f"{column_label} has missing values",
            "Missing values can make records incomplete and can break downstream matching, reporting, or decisions.",
            "Confirm whether the field is required. If it is, trace why values are missing and decide whether the source process or a quality expectation should change.",
            "COMPLETENESS",
        ),
        (
            ("duplicate", "non-unique", "not unique"),
            f"{column_label} may contain duplicate values",
            "Unexpected duplicates can cause the same business entity or transaction to be counted or acted on more than once.",
            "Check whether duplicates are allowed for this field. If not, review examples and identify whether the duplication comes from the source or the load process.",
            "UNIQUENESS",
        ),
        (
            ("whitespace", "leading space", "trailing space"),
            f"{column_label} contains extra spacing",
            "Extra spaces can make identical values look different during matching, filtering, and reporting.",
            "Review examples and decide whether the source should be corrected or whether whitespace should be standardized during ingestion.",
            "CONSISTENCY",
        ),
        (
            ("case", "capital", "upper", "lower"),
            f"{column_label} uses inconsistent capitalization",
            "Inconsistent capitalization can split what should be one category into several apparent values.",
            "Confirm the expected capitalization standard and decide whether to standardize values or document the variation as acceptable.",
            "CONSISTENCY",
        ),
        (
            ("format", "pattern", "regex", "mask"),
            f"{column_label} has inconsistent formatting",
            "Different formats can make validation, matching, search, and analytics less reliable.",
            "Review the observed formats, identify the business-approved format, and decide whether the data or the quality expectation needs to change.",
            "VALIDITY",
        ),
        (
            ("outlier", "unusual", "anomaly", "extreme"),
            f"{column_label} contains unusual values",
            "Unusual values may be legitimate exceptions, data-entry mistakes, or evidence that the field is being used inconsistently.",
            "Review the unusual examples with someone who understands the business process and classify them as valid exceptions or corrections.",
            "VALIDITY",
        ),
        (
            ("length", "too long", "too short"),
            f"{column_label} has unusual value lengths",
            "Unexpected lengths can indicate truncation, concatenated fields, misplaced values, or inconsistent entry practices.",
            "Compare the unusual values with the expected business format and determine whether the source data or the field definition needs correction.",
            "VALIDITY",
        ),
        (
            ("special", "character", "punctuation", "symbol"),
            f"{column_label} contains unexpected characters",
            "Unexpected characters can interfere with matching, exports, validation, or downstream systems.",
            "Review examples and determine whether the characters are meaningful business data or should be standardized or removed.",
            "VALIDITY",
        ),
        (
            ("constant", "single value", "low cardinality", "no variation"),
            f"{column_label} has little or no variation",
            "A field that rarely changes may be correct, but it can also indicate a default value, incomplete capture, or a field that is no longer useful.",
            "Confirm whether this field is expected to have more than one value. If not, document the behavior; otherwise investigate the source process.",
            "PROFILE",
        ),
        (
            ("semantic", "meaning", "type detection"),
            f"Review the detected meaning of {column_label}",
            "The detected business meaning influences validation, classification, and the expectations AI Data Steward may suggest.",
            "Confirm that the detected meaning matches how the business actually uses this field.",
            "SEMANTIC",
        ),
    ]

    for keywords, title, why, action, category in patterns:
        if any(keyword in text for keyword in keywords):
            return title, why, action, category

    clean_kind = kind.replace("_", " ").replace("-", " ").strip()
    clean_kind = " ".join(clean_kind.split())
    title = (
        f"Review {column_label}: {clean_kind}"
        if clean_kind and clean_kind.lower() != "profiling finding"
        else f"Review an unusual pattern in {column_label}"
    )
    return (
        title,
        "TestGen found a data characteristic that may be normal for this source or may indicate a quality concern.",
        "Review the evidence, confirm the expected business behavior, and decide whether this is acceptable, needs correction, needs a quality expectation, or needs expert review.",
        "PROFILE",
    )


def _hygiene_fingerprint(raw, index):
    identity = {
        "column": _display_column(raw).lower(),
        "kind": _hygiene_kind(raw).lower(),
    }
    # If TestGen exposes a durable ID, include it. Otherwise column+kind gives
    # stable decisions across repeat profiles even when counts/examples change.
    external_id = _first_recursive_value(
        raw,
        ("id", "issue_id", "hygiene_issue_id", "definition_id"),
    )
    if external_id not in (None, ""):
        identity["external_id"] = str(external_id)

    if identity["column"] == "this field" and identity["kind"] == "profiling finding":
        identity["fallback"] = index

    digest = hashlib.sha1(
        json.dumps(identity, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"hygiene-item:{digest}"



def _safe_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else round(number, 3)
    except (TypeError, ValueError):
        return None


def _profile_column_name(item):
    if not isinstance(item, dict):
        return None
    value = (
        item.get("column_name")
        or item.get("column")
        or item.get("name")
        or item.get("field_name")
    )
    if isinstance(value, dict):
        value = value.get("name") or value.get("column_name")
    return str(value).strip() if value not in (None, "") else None


def _profile_context_for_column(column, profile_columns):
    if not column or column == "This field":
        return {}

    match = None
    for item in profile_columns or []:
        if _profile_column_name(item) == column:
            match = item
            break
    if not isinstance(match, dict):
        return {}

    def first(keys):
        return _first_recursive_value(match, keys)

    context = {
        "data_type": first(("data_type", "datatype", "type_name")),
        "semantic_type": first(("semantic_type", "semantic", "semantic_name")),
        "row_count": _safe_number(first(("record_ct", "row_count", "record_count", "rows"))),
        "distinct_count": _safe_number(first(("distinct_count", "distinct_ct", "unique_count", "cardinality"))),
        "null_count": _safe_number(first(("null_count", "null_ct", "missing_count", "blank_count"))),
        "null_percent": _normalize_percent(first(("null_percent", "null_pct", "missing_percent", "missing_pct"))),
        "min_value": first(("min_value", "minimum", "min")),
        "max_value": first(("max_value", "maximum", "max")),
        "min_length": _safe_number(first(("min_length", "minimum_length", "shortest_length"))),
        "max_length": _safe_number(first(("max_length", "maximum_length", "longest_length"))),
        "avg_length": _safe_number(first(("avg_length", "average_length", "mean_length"))),
    }

    # Look for common/top values without assuming one TestGen schema shape.
    top_values = []
    candidates = _recursive_values(
        match,
        {
            "top_values", "frequent_values", "most_common_values",
            "value_frequencies", "top_value", "most_common",
        },
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            for entry in candidate:
                if isinstance(entry, dict):
                    value = (
                        entry.get("value")
                        or entry.get("name")
                        or entry.get("key")
                    )
                    count = (
                        entry.get("count")
                        or entry.get("frequency")
                        or entry.get("record_count")
                    )
                    if value not in (None, ""):
                        top_values.append(
                            {"value": value, "count": _safe_number(count)}
                        )
                elif entry not in (None, ""):
                    top_values.append({"value": entry, "count": None})
        elif isinstance(candidate, dict):
            for value, count in list(candidate.items())[:8]:
                top_values.append(
                    {"value": value, "count": _safe_number(count)}
                )

    deduped = []
    seen = set()
    for item in top_values:
        marker = repr(item.get("value"))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
        if len(deduped) >= 5:
            break
    context["typical_values"] = deduped

    return {
        key: value
        for key, value in context.items()
        if value not in (None, "", [], {})
    }



def _testgen_hygiene_evidence(raw):
    detail = _first_recursive_value(raw, ("detail", "details"))
    parsed = _parse_testgen_detail(detail)
    issue_name = str(raw.get("issue_type_name") or _hygiene_kind(raw))
    likelihood = raw.get("likelihood")
    impact = raw.get("impact_dimension")
    disposition = raw.get("disposition")

    evidence = {
        "issue_type_name": issue_name,
        "issue_type_code": raw.get("issue_type"),
        "detail": detail,
        "likelihood": likelihood,
        "impact_dimension": impact,
        "disposition": disposition,
        "records_profiled": parsed.get("records"),
        "empty_string_count": parsed.get("empty_string_count"),
        "null_count": parsed.get("null_count"),
        "dummy_value_count": parsed.get("dummy_value_count"),
        "non_alpha_count": parsed.get("non_alpha_count"),
        "semantic_type": parsed.get("semantic_type"),
        "minimum_value": parsed.get("minimum_value"),
        "patterns": parsed.get("patterns"),
    }

    affected = _hygiene_count(raw)
    if affected is not None:
        evidence["affected_count"] = affected
        if parsed.get("records"):
            evidence["affected_percent"] = round(
                affected / parsed["records"] * 100,
                1,
            )

    return {
        key: value
        for key, value in evidence.items()
        if value not in (None, "", [], {})
    }


def _raw_evidence(raw):
    evidence = _testgen_hygiene_evidence(raw)

    observed = _hygiene_examples(raw)
    if observed:
        evidence["observed_values"] = observed

    for label, keys in {
        "message": ("message", "description", "reason"),
        "expected": ("expected", "expected_value", "expected_pattern", "expectation"),
        "actual": ("actual", "actual_value", "observed", "observed_value"),
        "frequency": ("frequency", "occurrence_count", "value_count"),
        "percent": ("percent", "percentage", "pct", "rate"),
    }.items():
        value = _first_recursive_value(raw, keys)
        if value not in (None, "", [], {}):
            evidence[label] = value

    return evidence


def _evidence_sufficiency(raw_evidence, profile_context):
    score = 0
    reasons = []

    if raw_evidence.get("observed_values"):
        score += 2
    elif raw_evidence.get("detail"):
        score += 1
        reasons.append(
            "TestGen returned aggregate evidence, but not example source values."
        )
    else:
        reasons.append("No example values were returned by TestGen.")

    if raw_evidence.get("affected_count") is not None:
        score += 2
    else:
        reasons.append("TestGen did not return an affected-record count.")

    if raw_evidence.get("records_profiled") is not None:
        score += 1

    if (
        raw_evidence.get("patterns")
        or raw_evidence.get("semantic_type")
        or raw_evidence.get("minimum_value")
    ):
        score += 1

    if profile_context:
        score += 2
    else:
        reasons.append(
            "The TestGen column-profile endpoint did not return statistics for this finding."
        )

    if profile_context.get("typical_values"):
        score += 1

    if score >= 5:
        level = "HIGH"
        guidance = (
            "The current TestGen evidence is strong enough to support an informed "
            "stewardship review, but source verification may still be appropriate."
        )
    elif score >= 3:
        level = "MEDIUM"
        guidance = (
            "The current evidence provides useful context, but you should verify the "
            "source record or confirm the expected business behavior before making a "
            "high-impact decision."
        )
    else:
        level = "LOW"
        guidance = (
            "There is not enough evidence in the current TestGen response to support "
            "a confident decision by itself. Verify the source record, add notes from "
            "a business expert, or choose expert review rather than guessing."
        )

    return {
        "level": level,
        "guidance": guidance,
        "limitations": reasons,
    }


def _attach_finding_evidence(finding, raw, profile_columns):
    raw_evidence = _raw_evidence(raw)
    profile_context = _profile_context_for_column(
        finding.get("column"),
        profile_columns,
    )
    finding["evidence"] = {
        "testgen": raw_evidence,
        "profile_context": profile_context,
        "source_record_context": {
            "available": False,
            "message": (
                "Source-row lookup is not available through the current TestGen "
                "integration. Use the source system or a future read-only evidence "
                "connector to verify the exact record when needed."
            ),
        },
        "sufficiency": _evidence_sufficiency(
            raw_evidence,
            profile_context,
        ),
    }
    return finding


def _normalize_hygiene_findings(hygiene_items, previous_findings=None, profile_columns=None):
    previous = {
        item.get("fingerprint"): item
        for item in (previous_findings or [])
        if isinstance(item, dict) and item.get("fingerprint")
    }

    findings = []
    for index, raw in enumerate(hygiene_items, start=1):
        if not isinstance(raw, dict):
            raw = {"value": raw}

        column = _display_column(raw)
        kind = _hygiene_kind(raw)
        title, why, action, category = _hygiene_plain_language(column, kind)
        fingerprint = _hygiene_fingerprint(raw, index)
        prior = previous.get(fingerprint, {})

        confidence = _first_recursive_value(
            raw,
            ("confidence", "confidence_level", "likelihood", "severity", "level"),
        )
        if isinstance(confidence, dict):
            confidence = confidence.get("value") or confidence.get("name")

        finding = {
            "fingerprint": fingerprint,
            "number": index,
            "column": column,
            "category": category,
            "testgen_finding": kind,
            "title": title,
            "why_it_matters": why,
            "recommended_action": action,
            "affected_count": _hygiene_count(raw),
            "confidence": str(confidence).upper() if confidence not in (None, "") else None,
            "examples": _hygiene_examples(raw),
            "review_status": prior.get("review_status", "PENDING"),
            "decision": prior.get("decision"),
            "notes": prior.get("notes"),
            "reviewed_by": prior.get("reviewed_by"),
            "reviewed_at": prior.get("reviewed_at"),
        }
        _attach_finding_evidence(
            finding,
            raw,
            profile_columns or [],
        )
        findings.append(finding)

    return findings


def _hygiene_summary(findings):
    total = len(findings)
    resolved = sum(
        1 for item in findings
        if item.get("review_status") == "RESOLVED"
    )
    escalated = sum(
        1 for item in findings
        if item.get("review_status") == "ESCALATED"
    )
    pending = max(0, total - resolved - escalated)
    categories = {}
    for item in findings:
        category = item.get("category") or "PROFILE"
        categories[category] = categories.get(category, 0) + 1
    return {
        "total": total,
        "pending": pending,
        "resolved": resolved,
        "escalated": escalated,
        "categories": categories,
    }


def enrich_hygiene_issue(issue: QualityIssue):
    """Backfill Stage 3.5.2 steward findings from stored raw TestGen evidence."""
    if issue.issue_type != "HYGIENE_FINDING":
        return issue

    details = dict(issue.details or {})
    raw = details.get("hygiene_issues") or []
    existing = details.get("steward_findings") or []
    findings = _normalize_hygiene_findings(
        raw,
        existing,
        details.get("profile_columns") or [],
    )
    details["steward_findings"] = findings
    details["finding_summary"] = _hygiene_summary(findings)
    details["finding_count"] = len(findings)
    issue.details = details
    return issue


def decide_hygiene_finding(
    db: Session,
    issue: QualityIssue,
    actor_id: int,
    finding_fingerprint: str,
    decision_type: str,
    notes: str | None = None,
):
    allowed = {
        "BAD_DATA",
        "VALID_EXCEPTION",
        "EXPECTATION_NEEDS_CHANGE",
        "EXPERT_REVIEW",
    }
    if decision_type not in allowed:
        raise ValueError("Unsupported hygiene finding decision.")

    enrich_hygiene_issue(issue)
    details = dict(issue.details or {})
    findings = list(details.get("steward_findings") or [])

    target = None
    for finding in findings:
        if finding.get("fingerprint") == finding_fingerprint:
            target = finding
            break
    if not target:
        raise ValueError("Profiling finding not found.")

    target["decision"] = decision_type
    target["notes"] = notes
    target["reviewed_by"] = actor_id
    target["reviewed_at"] = now().isoformat()
    target["review_status"] = (
        "ESCALATED" if decision_type == "EXPERT_REVIEW" else "RESOLVED"
    )

    summary = _hygiene_summary(findings)
    details["steward_findings"] = findings
    details["finding_summary"] = summary
    issue.details = details

    db.add(
        QualityDecision(
            issue_id=issue.id,
            actor_id=actor_id,
            decision_type=f"HYGIENE_{decision_type}",
            notes=(
                f"{target.get('title')}: {notes}"
                if notes
                else target.get("title")
            ),
        )
    )

    if summary["pending"] == 0:
        if summary["escalated"] > 0:
            issue.status = "NEEDS_EXPERT_REVIEW"
            issue.resolved_at = None
            issue.title = (
                f"{summary['escalated']} profiling "
                f"{'finding needs' if summary['escalated'] == 1 else 'findings need'} "
                "expert review"
            )
            _reopen_issue_task(db, issue)
        else:
            issue.status = "RESOLVED"
            issue.resolved_at = now()
            _complete_issue_tasks(db, issue.id)
    else:
        issue.status = "OPEN"
        issue.resolved_at = None
        issue.title = (
            f"Review {summary['pending']} of {summary['total']} "
            "TestGen profiling findings"
        )
        _reopen_issue_task(db, issue)

    db.commit()
    return issue


def _upsert_hygiene_issue(
    db: Session,
    *,
    asset: DataAsset,
    resource_id: int,
    run_id: str,
    hygiene_items: list,
    pii_items: list,
    column_items: list,
):
    existing = db.scalars(
        select(QualityIssue)
        .where(
            QualityIssue.asset_id == asset.id,
            QualityIssue.resource_id == resource_id,
            QualityIssue.issue_type == "HYGIENE_FINDING",
            QualityIssue.source == "TESTGEN",
        )
        .order_by(QualityIssue.created_at.asc())
    ).all()

    open_existing = [
        issue for issue in existing
        if issue.status not in {"RESOLVED"}
    ]

    # Stage 3.3 could create one issue on every profiling run.
    # Consolidate all of those into one durable stewardship issue.
    canonical = open_existing[0] if open_existing else None

    if not hygiene_items:
        for issue in open_existing:
            _resolve_issue(
                db,
                issue,
                reason="Latest TestGen profile no longer reports hygiene findings.",
            )
        return None

    title = (
        f"Review {len(hygiene_items)} TestGen profiling "
        f"{'finding' if len(hygiene_items) == 1 else 'findings'}"
    )
    previous_findings = (
        (canonical.details or {}).get("steward_findings", [])
        if canonical
        else []
    )
    steward_findings = _normalize_hygiene_findings(
        hygiene_items,
        previous_findings,
        column_items,
    )
    finding_summary = _hygiene_summary(steward_findings)

    details = {
        "fingerprint": f"hygiene:{asset.id}:{resource_id}",
        "finding_kind": "PROFILING",
        "latest_run_id": run_id,
        "hygiene_issues": hygiene_items,
        "profile_columns": column_items,
        "steward_findings": steward_findings,
        "finding_summary": finding_summary,
        "potential_pii": pii_items,
        "potential_pii_count": len(pii_items),
        "profile_column_count": len(column_items),
        "finding_count": len(hygiene_items),
    }

    if canonical:
        canonical.title = (
            f"Review {finding_summary['pending']} of "
            f"{finding_summary['total']} TestGen profiling findings"
            if finding_summary["pending"] != finding_summary["total"]
            else title
        )
        canonical.description = (
            "TestGen profiling identified data characteristics that may "
            "need stewardship review. AI Data Steward translates each "
            "finding into plain language and lets you resolve them one at a time."
        )
        canonical.severity = "MEDIUM"
        canonical.status = "OPEN"
        canonical.resolved_at = None
        canonical.external_run_id = run_id
        canonical.details = details
        _reopen_issue_task(db, canonical)
    else:
        canonical = QualityIssue(
            organization_id=asset.organization_id,
            asset_id=asset.id,
            resource_id=resource_id,
            issue_type="HYGIENE_FINDING",
            title=title,
            description=(
                "TestGen profiling identified data characteristics that may "
                "need stewardship review. AI Data Steward translates each "
                "finding into plain language and lets you resolve them one at a time."
            ),
            severity="MEDIUM",
            source="TESTGEN",
            external_run_id=run_id,
            details=details,
        )
        db.add(canonical)
        db.flush()
        _open_task_for_issue(db, canonical)

    # Resolve any duplicate open issues from earlier Stage 3.3 runs.
    for duplicate in open_existing[1:]:
        _resolve_issue(
            db,
            duplicate,
            reason="Consolidated into the current TestGen profiling finding.",
        )

    return canonical


def _upsert_test_failure_issue(
    db: Session,
    *,
    asset: DataAsset,
    resource_id: int,
    run_id: str,
    item: dict,
    index: int,
):
    fingerprint = _test_result_key(item, index)
    evidence = _evidence_from_test_result(item, index)
    name = evidence["check_name"]

    candidates = db.scalars(
        select(QualityIssue).where(
            QualityIssue.asset_id == asset.id,
            QualityIssue.resource_id == resource_id,
            QualityIssue.issue_type == "TESTGEN_TEST_FAILURE",
            QualityIssue.source == "TESTGEN",
        )
    ).all()

    issue = next(
        (candidate for candidate in candidates if _issue_key(candidate) == fingerprint),
        None,
    )

    failed_count = evidence["failed_count"]
    description = f"TestGen reported a failed quality check: {name}."
    if failed_count is not None:
        description += f" {failed_count:,} records failed."
    elif evidence["message"]:
        description += f" {evidence['message']}"

    details = {
        "fingerprint": fingerprint,
        "finding_kind": "TEST_FAILURE",
        "latest_run_id": run_id,
        "evidence": evidence,
        "sample_values": evidence["sample_values"],
        "evaluated_count": evidence["evaluated_count"],
        "score": evidence["score"],
        "testgen_result": item,
    }

    external_id = (
        item.get("test_definition_id")
        or item.get("test_id")
        or item.get("id")
    )

    if issue:
        issue.title = f"Investigate quality failure: {name}"
        issue.description = description
        issue.severity = "HIGH"
        issue.status = "OPEN"
        issue.resolved_at = None
        issue.failed_count = failed_count
        issue.external_run_id = run_id
        issue.external_issue_id = (
            str(external_id) if external_id is not None else None
        )
        issue.details = details
        _reopen_issue_task(db, issue)
        return issue

    issue = QualityIssue(
        organization_id=asset.organization_id,
        asset_id=asset.id,
        resource_id=resource_id,
        issue_type="TESTGEN_TEST_FAILURE",
        title=f"Investigate quality failure: {name}",
        description=description,
        severity="HIGH",
        failed_count=failed_count,
        source="TESTGEN",
        external_run_id=run_id,
        external_issue_id=(
            str(external_id) if external_id is not None else None
        ),
        details=details,
    )
    db.add(issue)
    db.flush()
    _open_task_for_issue(db, issue)
    return issue


def _resolve_cleared_test_failures(
    db: Session,
    *,
    asset: DataAsset,
    resource_id: int,
    active_fingerprints: set[str],
):
    issues = db.scalars(
        select(QualityIssue).where(
            QualityIssue.asset_id == asset.id,
            QualityIssue.resource_id == resource_id,
            QualityIssue.issue_type == "TESTGEN_TEST_FAILURE",
            QualityIssue.source == "TESTGEN",
        )
    ).all()

    for issue in issues:
        if issue.status == "RESOLVED":
            continue
        if _issue_key(issue) not in active_fingerprints:
            _resolve_issue(
                db,
                issue,
                reason=(
                    "Latest TestGen test run no longer reports this failure."
                ),
            )


def reconcile_asset_quality_issues(db: Session, asset: DataAsset):
    """
    Clean up duplicate Stage 3.3 hygiene findings even before another profile
    is run. The Stewardship Inbox already synchronizes on read, so this gives
    existing installations a no-migration cleanup path.
    """
    resource_ids = [link.resource_id for link in asset.resources]
    if not resource_ids:
        return

    for resource_id in resource_ids:
        hygiene = db.scalars(
            select(QualityIssue)
            .where(
                QualityIssue.asset_id == asset.id,
                QualityIssue.resource_id == resource_id,
                QualityIssue.issue_type == "HYGIENE_FINDING",
                QualityIssue.source == "TESTGEN",
                QualityIssue.status != "RESOLVED",
            )
            .order_by(QualityIssue.created_at.desc())
        ).all()

        if len(hygiene) <= 1:
            continue

        canonical = hygiene[0]
        details = dict(canonical.details or {})
        details["fingerprint"] = f"hygiene:{asset.id}:{resource_id}"
        details["deduplicated_issue_count"] = len(hygiene) - 1
        canonical.details = details
        _reopen_issue_task(db, canonical)

        for duplicate in hygiene[1:]:
            _resolve_issue(
                db,
                duplicate,
                reason="Consolidated by Stage 3.4 duplicate reconciliation.",
            )

    db.flush()

def assess_resource(db: Session, asset: DataAsset, resource_id: int):
    link = get_link(db, resource_id)
    if not link:
        link = ensure_link(
            db,
            organization_id=asset.organization_id,
            resource_id=resource_id,
            payload=None,
        )

    try:
        if settings.testgen_mode == "real":
            if not link.table_group_id:
                raise HTTPException(
                    status_code=400,
                    detail="Link this resource to a TestGen table group first.",
                )

            client = TestGenClient()
            submission = client.submit_profile(link.table_group_id)
            run_id = submission.get("id")
            if not run_id:
                raise TestGenError(
                    "TestGen profiling submission did not return a job id."
                )

            result = client.wait_for_profile(run_id)

            # Pull real 5.92 profiling detail endpoints after completion.
            columns = client.get_profile_columns(run_id)
            hygiene = client.get_hygiene_issues(run_id)
            try:
                pii = client.get_potential_pii(run_id)
            except TestGenError:
                # PII detail should not make an otherwise successful profile fail.
                pii = {"items": []}

            suggestions = []

            summary = result.get("result") or {}
            score = _normalize_percent(
                _recursive_number(
                    summary,
                    ("dq_score", "quality_score", "score"),
                )
            )

            # TestGen may not include a DQ score in the profiling response.
            # Preserve a prior score if available; otherwise display 0.0 until
            # a real test run supplies quality evidence.
            if score is None:
                previous = db.scalar(
                    select(QualityProfile)
                    .where(
                        QualityProfile.asset_id == asset.id,
                        QualityProfile.resource_id == resource_id,
                    )
                    .order_by(QualityProfile.profiled_at.desc())
                    .limit(1)
                )
                score = previous.overall_score if previous else 0.0

            row_count_value = _recursive_number(
                summary,
                ("record_ct", "row_count", "record_count", "rows"),
            )
            row_count = (
                int(row_count_value)
                if row_count_value is not None
                else None
            )

            profile = QualityProfile(
                asset_id=asset.id,
                resource_id=resource_id,
                overall_score=score,
                row_count=row_count,
                source="TESTGEN",
                external_run_id=run_id,
            )
            db.add(profile)

            hygiene_items = _items(hygiene)
            pii_items = _items(pii)
            column_items = _items(columns)

            _upsert_hygiene_issue(
                db,
                asset=asset,
                resource_id=resource_id,
                run_id=run_id,
                hygiene_items=hygiene_items,
                pii_items=pii_items,
                column_items=column_items,
            )

            hygiene_count = len(hygiene_items)

        else:
            result = MockTestGenClient().profile(link.external_table_name)
            run_id = result["id"]
            suggestions = result.get("suggested_expectations", [])
            summary = result.get("result") or {}
            score = round(float(summary.get("score") or 0) * 100, 1)

            profile = QualityProfile(
                asset_id=asset.id,
                resource_id=resource_id,
                overall_score=score,
                completeness_score=min(100.0, score + 5.0),
                validity_score=max(0.0, score - 1.5),
                uniqueness_score=min(100.0, score + 7.0),
                consistency_score=max(0.0, score - 3.0),
                timeliness_score=max(0.0, score - 8.0),
                row_count=summary.get("record_ct"),
                source="TESTGEN",
                external_run_id=run_id,
            )
            db.add(profile)

            hygiene_counts = (
                summary.get("issue_counts", {})
                .get("hygiene_issues", {})
            )
            hygiene_count = sum(
                int(hygiene_counts.get(k, 0) or 0)
                for k in ("definite", "likely", "possible")
            )

            if hygiene_count:
                issue = QualityIssue(
                    organization_id=asset.organization_id,
                    asset_id=asset.id,
                    resource_id=resource_id,
                    issue_type="HYGIENE_FINDING",
                    title=f"Review {hygiene_count} profiling findings",
                    description=(
                        "Profiling found data characteristics that may "
                        "require a stewardship decision."
                    ),
                    severity="MEDIUM",
                    source="TESTGEN",
                    external_run_id=run_id,
                    details={
                        "issue_counts": summary.get("issue_counts", {})
                    },
                )
                db.add(issue)
                db.flush()
                _open_task_for_issue(db, issue)

        for spec in suggestions:
            exists = db.scalar(
                select(QualityRule).where(
                    QualityRule.asset_id == asset.id,
                    QualityRule.resource_id == resource_id,
                    QualityRule.rule_name == spec["name"],
                )
            )
            if not exists:
                db.add(
                    QualityRule(
                        asset_id=asset.id,
                        resource_id=resource_id,
                        rule_name=spec["name"],
                        rule_type=spec["rule_type"],
                        plain_language_rule=spec["plain_language_rule"],
                        rule_definition=spec["definition"],
                        status="PROPOSED",
                    )
                )

    except TestGenError as exc:
        link.sync_status = "ERROR"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    link.last_profiled_at = now()
    link.last_external_run_id = run_id
    link.sync_status = "SYNCED"
    db.commit()

    return {
        "profile_run_id": run_id,
        "overall_score": score,
        "suggested_expectations": len(suggestions),
        "hygiene_findings": hygiene_count,
    }


def run_tests(db: Session, asset: DataAsset, resource_id: int):
    link = get_link(db, resource_id)
    if not link:
        raise HTTPException(
            status_code=400,
            detail=(
                "Assess this resource first so it is linked "
                "to the quality engine."
            ),
        )

    approved_rules = db.scalars(
        select(QualityRule).where(
            QualityRule.asset_id == asset.id,
            QualityRule.resource_id == resource_id,
            QualityRule.status == "APPROVED",
        )
    ).all()

    if settings.testgen_mode != "real" and not approved_rules:
        raise HTTPException(
            status_code=400,
            detail="Approve at least one suggested quality expectation first.",
        )

    try:
        if settings.testgen_mode == "real":
            if not link.test_suite_id:
                raise HTTPException(
                    status_code=400,
                    detail="Add the TestGen test suite ID before running checks.",
                )

            client = TestGenClient()
            submission = client.submit_test_run(link.test_suite_id)
            run_id = submission.get("id")
            if not run_id:
                raise TestGenError(
                    "TestGen test-run submission did not return a job id."
                )

            result = client.wait_for_test_run(run_id)
            result_page = client.get_test_results(run_id)
            test_items = _items(result_page)
            failures = [
                item for item in test_items if _is_failure(item)
            ]

            score = _quality_score_from_results(test_items)

            active_fingerprints = set()
            for index, item in enumerate(failures, start=1):
                active_fingerprints.add(_test_result_key(item, index))
                _upsert_test_failure_issue(
                    db,
                    asset=asset,
                    resource_id=resource_id,
                    run_id=run_id,
                    item=item,
                    index=index,
                )

            # If an older TestGen failure is absent from the newest run,
            # automatically close that stale issue and its Inbox task.
            _resolve_cleared_test_failures(
                db,
                asset=asset,
                resource_id=resource_id,
                active_fingerprints=active_fingerprints,
            )

            db.add(
                QualityProfile(
                    asset_id=asset.id,
                    resource_id=resource_id,
                    overall_score=score,
                    source="TESTGEN",
                    external_run_id=run_id,
                )
            )

            failed_total = len(failures)

        else:
            result = MockTestGenClient().run_tests()
            run_id = result["id"]
            failures = result.get("failures", [])
            summary = result.get("result") or {}
            failed_total = int(
                (summary.get("result_counts") or {}).get("failed", 0) or 0
            )

            by_name = {r.rule_name: r for r in approved_rules}
            for failure in failures:
                rule = by_name.get(failure["rule_name"])
                if not rule:
                    continue

                db.add(
                    QualityResult(
                        rule_id=rule.id,
                        result_status="FAIL",
                        evaluated_count=failure["evaluated_count"],
                        failed_count=failure["failed_count"],
                        score=failure["score"],
                        details={
                            "message": failure["description"],
                            "sample_values":
                                failure.get("sample_values", []),
                        },
                        source="TESTGEN",
                        external_run_id=run_id,
                    )
                )

                issue = QualityIssue(
                    organization_id=asset.organization_id,
                    asset_id=asset.id,
                    resource_id=resource_id,
                    rule_id=rule.id,
                    issue_type="RULE_FAILURE",
                    title=(
                        f"Investigate quality failure: {rule.rule_name}"
                    ),
                    description=failure["description"],
                    severity="HIGH",
                    failed_count=failure["failed_count"],
                    source="TESTGEN",
                    external_run_id=run_id,
                    details={
                        "sample_values":
                            failure.get("sample_values", []),
                        "score": failure["score"],
                    },
                )
                db.add(issue)
                db.flush()
                _open_task_for_issue(db, issue)

            score = round(
                float(summary.get("score") or 0) * 100,
                1,
            )
            if score:
                db.add(
                    QualityProfile(
                        asset_id=asset.id,
                        resource_id=resource_id,
                        overall_score=score,
                        source="TESTGEN",
                        external_run_id=run_id,
                    )
                )

    except TestGenError as exc:
        link.sync_status = "ERROR"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    link.last_tested_at = now()
    link.last_external_run_id = run_id
    link.sync_status = "SYNCED"
    db.commit()

    return {
        "test_run_id": run_id,
        "score": score,
        "failed_checks": failed_total,
    }

def decide_issue(db: Session, issue: QualityIssue, actor_id: int, decision_type: str, notes: str | None):
    allowed = {'BAD_DATA','VALID_EXCEPTION','EXPECTATION_NEEDS_CHANGE','EXPERT_REVIEW'}
    if decision_type not in allowed:
        raise HTTPException(status_code=400, detail=f'Decision must be one of: {", ".join(sorted(allowed))}')
    db.add(QualityDecision(issue_id=issue.id, decision_type=decision_type, notes=notes, decided_by=actor_id))
    if decision_type != 'EXPERT_REVIEW':
        issue.status = 'RESOLVED'
        issue.resolved_at = now()
        _complete_issue_tasks(db, issue.id)
    else:
        issue.status = 'NEEDS_EXPERT_REVIEW'
        issue.resolved_at = None
        _reopen_issue_task(db, issue)
    db.commit()
