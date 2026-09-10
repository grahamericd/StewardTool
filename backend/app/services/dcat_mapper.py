def map_snapshot_to_dcat(snapshot: dict, organization_name: str) -> dict:
    asset = snapshot["asset"]
    metadata = snapshot.get("metadata", {})
    resources = snapshot.get("resources", [])
    quality = snapshot.get("quality")

    dataset_uri = f"urn:ai-data-steward:dataset:{asset['asset_identifier']}"

    distributions = []
    services = []
    for resource in resources:
        base = {"@id": f"urn:ai-data-steward:resource:{resource['resource_id']}", "dct:title": resource["name"]}
        if resource.get("description"):
            base["dct:description"] = resource["description"]
        if resource.get("format"):
            base["dct:format"] = resource["format"]
        if resource.get("media_type"):
            base["dcat:mediaType"] = resource["media_type"]
        if resource.get("location_reference"):
            base["dcat:accessURL"] = resource["location_reference"]

        if resource["resource_type"] == "API":
            services.append({**base, "@type": "dcat:DataService", "dcat:servesDataset": {"@id": dataset_uri}})
        else:
            distributions.append({**base, "@type": "dcat:Distribution"})

    dataset = {
        "@id": dataset_uri,
        "@type": "dcat:Dataset",
        "dct:identifier": asset["asset_identifier"],
        "dct:title": asset["name"],
        "dct:description": asset.get("business_definition") or "",
        "dct:publisher": {"@type": "foaf:Agent", "foaf:name": organization_name},
    }
    if metadata.get("theme"):
        dataset["dcat:theme"] = metadata["theme"]
    if metadata.get("keyword"):
        dataset["dcat:keyword"] = metadata["keyword"]
    if metadata.get("update_frequency"):
        dataset["dct:accrualPeriodicity"] = metadata["update_frequency"]
    if metadata.get("contact"):
        dataset["dcat:contactPoint"] = metadata["contact"]
    if distributions:
        dataset["dcat:distribution"] = distributions
    if quality and quality.get("overall_score") is not None:
        dataset["dqv:hasQualityMeasurement"] = {
            "@type": "dqv:QualityMeasurement",
            "dqv:value": quality["overall_score"],
            "dct:description": "Latest AI Data Steward overall data quality score (0-100).",
        }

    return {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "foaf": "http://xmlns.com/foaf/0.1/",
            "dqv": "http://www.w3.org/ns/dqv#",
        },
        "@graph": [dataset] + services,
    }
