from abc import ABC, abstractmethod
from datetime import datetime, timezone
import re

import httpx

from ..config import settings


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return value[:90] or "dataset"


class CatalogPublisher(ABC):
    @abstractmethod
    def publish(self, *, release_id: int, snapshot: dict, dcat_payload: dict, existing_ckan_name: str | None = None) -> dict:
        raise NotImplementedError


class MockCKANPublisher(CatalogPublisher):
    def publish(self, *, release_id: int, snapshot: dict, dcat_payload: dict, existing_ckan_name: str | None = None) -> dict:
        dataset = dcat_payload["@graph"][0]
        slug = existing_ckan_name or slugify(dataset["dct:title"])
        return {
            "success": True,
            "publisher": "mock-ckan",
            "release_id": release_id,
            "ckan_dataset_id": f"mock-{release_id}",
            "ckan_name": slug,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "message": "Published successfully to the Stage 2 mock CKAN adapter.",
        }


class CKANPublisher(CatalogPublisher):
    def __init__(self):
        if not settings.ckan_base_url or not settings.ckan_api_key:
            raise RuntimeError("CKAN_BASE_URL and CKAN_API_KEY are required for real CKAN publishing")
        self.base = settings.ckan_base_url.rstrip("/")
        self.headers = {"Authorization": settings.ckan_api_key}

    def _action(self, name: str, payload: dict):
        url = f"{self.base}/api/3/action/{name}"
        response = httpx.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"CKAN action {name} failed: {body}")
        return body["result"]

    def publish(self, *, release_id: int, snapshot: dict, dcat_payload: dict, existing_ckan_name: str | None = None) -> dict:
        asset = snapshot["asset"]
        metadata = snapshot.get("metadata", {})
        resources = snapshot.get("resources", [])
        name = existing_ckan_name or slugify(asset["name"] + "-" + asset["asset_identifier"][:8])

        pkg = {
            "name": name,
            "title": asset["name"],
            "notes": asset.get("business_definition") or "",
            "owner_org": settings.ckan_owner_org,
            "tags": [{"name": str(x)} for x in (metadata.get("keyword") if isinstance(metadata.get("keyword"), list) else [metadata.get("keyword")]) if x],
            "extras": [
                {"key": "ai_data_steward_asset_id", "value": asset["asset_identifier"]},
                {"key": "business_domain", "value": str(asset.get("business_domain") or "")},
                {"key": "classification", "value": str(asset.get("classification") or "")},
                {"key": "governance_dcat_jsonld", "value": __import__("json").dumps(dcat_payload)},
            ],
        }
        if not pkg["owner_org"]:
            pkg.pop("owner_org")

        action = "package_patch" if existing_ckan_name else "package_create"
        if existing_ckan_name:
            pkg["id"] = existing_ckan_name
        result = self._action(action, pkg)

        for resource in resources:
            if not resource.get("location_reference"):
                continue
            self._action("resource_create", {
                "package_id": result["id"],
                "name": resource["name"],
                "url": resource["location_reference"],
                "format": resource.get("format") or resource.get("resource_type") or "",
                "description": resource.get("description") or "",
            })

        return {
            "success": True,
            "publisher": "ckan",
            "release_id": release_id,
            "ckan_dataset_id": result["id"],
            "ckan_name": result["name"],
            "published_at": datetime.now(timezone.utc).isoformat(),
            "message": "Published successfully to CKAN.",
        }


def get_publisher():
    return CKANPublisher() if settings.catalog_publisher.lower() == "ckan" else MockCKANPublisher()
