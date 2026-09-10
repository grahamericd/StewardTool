from collections import defaultdict


def build_asset_snapshot(asset):
    metadata = defaultdict(list)
    for item in asset.metadata_items:
        if item.review_status == "APPROVED":
            metadata[item.metadata_key].append(item.metadata_value)

    normalized = {}
    for key, values in metadata.items():
        normalized[key] = values if len(values) > 1 else values[0]

    resources = []
    for link in asset.resources:
        r = link.resource
        resources.append({
            "resource_id": r.id,
            "name": r.name,
            "resource_type": r.resource_type,
            "structure_type": r.structure_type,
            "description": r.description,
            "location_reference": r.location_reference,
            "format": r.format,
            "media_type": r.media_type,
            "relationship_type": link.relationship_type,
            "is_authoritative": link.is_authoritative,
            "system": r.system.name if r.system else None,
        })

    quality_profiles = sorted(asset.quality_profiles, key=lambda x: x.profiled_at or 0, reverse=True)
    latest_profile = None
    if quality_profiles:
        q = quality_profiles[0]
        latest_profile = {
            "overall_score": q.overall_score,
            "completeness_score": q.completeness_score,
            "validity_score": q.validity_score,
            "uniqueness_score": q.uniqueness_score,
            "consistency_score": q.consistency_score,
            "timeliness_score": q.timeliness_score,
            "row_count": q.row_count,
            "profiled_at": q.profiled_at.isoformat() if q.profiled_at else None,
            "source": q.source,
        }

    return {
        "asset": {
            "asset_id": asset.id,
            "asset_identifier": asset.asset_identifier,
            "organization_id": asset.organization_id,
            "name": asset.name,
            "business_definition": asset.business_definition,
            "business_domain": asset.business_domain,
            "business_owner": asset.business_owner,
            "data_steward": asset.data_steward,
            "authoritative_status": asset.authoritative_status,
            "classification": asset.classification,
            "retention_requirement": asset.retention_requirement,
            "retention_authority": asset.retention_authority,
            "asset_status": asset.asset_status,
        },
        "metadata": normalized,
        "resources": resources,
        "quality": latest_profile,
    }
