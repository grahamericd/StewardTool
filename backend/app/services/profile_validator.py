PROFILE_FIELDS = [
    {
        "key": "business_definition", "title": "Business definition", "domain": "CATALOG",
        "weight": 12, "required": True,
        "guidance": "Describe the information in plain business language so someone outside your team can understand it.",
    },
    {
        "key": "business_owner", "title": "Business owner", "domain": "OWNERSHIP",
        "weight": 10, "required": True,
        "guidance": "Identify the business function with authority to make decisions about this information.",
    },
    {
        "key": "data_steward", "title": "Data steward", "domain": "OWNERSHIP",
        "weight": 8, "required": False,
        "guidance": "Identify who coordinates the day-to-day stewardship of this information.",
    },
    {
        "key": "has_resource", "title": "Where the information lives", "domain": "CATALOG",
        "weight": 10, "required": True,
        "guidance": "Identify at least one database, file, API, document collection, spreadsheet, or other resource.",
    },
    {
        "key": "theme", "title": "Business area", "domain": "METADATA",
        "weight": 8, "required": True,
        "guidance": "Choose the business area that best describes this information.",
    },
    {
        "key": "keywords", "title": "Search terms", "domain": "METADATA",
        "weight": 7, "required": False,
        "guidance": "Add words people might use when searching for this information.",
    },
    {
        "key": "update_frequency", "title": "Update frequency", "domain": "METADATA",
        "weight": 7, "required": False,
        "guidance": "Document how often the information normally changes or is refreshed.",
    },
    {
        "key": "contact", "title": "Contact point", "domain": "METADATA",
        "weight": 5, "required": False,
        "guidance": "Provide a person or mailbox that can answer questions about this information.",
    },
    {
        "key": "authoritative_source", "title": "Authoritative source", "domain": "GOVERNANCE",
        "weight": 10, "required": True,
        "guidance": "Confirm which resource should be relied on as the official source for business decisions.",
    },
    {
        "key": "classification", "title": "Classification", "domain": "CLASSIFICATION",
        "weight": 9, "required": False,
        "guidance": "Determine the handling classification appropriate for this information.",
    },
    {
        "key": "retention", "title": "Retention requirement", "domain": "LIFECYCLE",
        "weight": 6, "required": False,
        "guidance": "Document how long this information must be retained and the authority for that requirement.",
    },
    {
        "key": "quality", "title": "Data quality assessed", "domain": "QUALITY",
        "weight": 8, "required": False,
        "guidance": "For structured resources, profile quality and establish expectations that matter to the business use.",
    },
]


def evaluate_profile(snapshot: dict):
    asset = snapshot["asset"]
    metadata = snapshot.get("metadata", {})
    resources = snapshot.get("resources", [])
    quality = snapshot.get("quality")

    values = {
        "business_definition": bool(asset.get("business_definition")),
        "business_owner": bool(asset.get("business_owner")),
        "data_steward": bool(asset.get("data_steward")),
        "has_resource": bool(resources),
        "theme": bool(metadata.get("theme")),
        "keywords": bool(metadata.get("keyword")),
        "update_frequency": bool(metadata.get("update_frequency")),
        "contact": bool(metadata.get("contact")),
        "authoritative_source": any(r.get("is_authoritative") for r in resources),
        "classification": bool(asset.get("classification")),
        "retention": bool(asset.get("retention_requirement")),
        "quality": quality is not None,
    }

    total = sum(item["weight"] for item in PROFILE_FIELDS)
    earned = sum(item["weight"] for item in PROFILE_FIELDS if values[item["key"]])
    score = round(100 * earned / total) if total else 0

    checks = []
    blocking = []
    for item in PROFILE_FIELDS:
        complete = values[item["key"]]
        check = {**item, "complete": complete}
        checks.append(check)
        if item["required"] and not complete:
            blocking.append(item["key"])

    return {
        "score": score,
        "checks": checks,
        "missing": [c["key"] for c in checks if not c["complete"]],
        "blocking": blocking,
        "ready_to_submit": not blocking,
    }
