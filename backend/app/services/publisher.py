from datetime import datetime, timezone
class MockCKANPublisher:
    def publish(self, release_id, dcat_payload):
        title=dcat_payload["@graph"][0]["dct:title"]
        slug=title.lower().replace(" ","-").replace("/","-")
        return {"success":True,"publisher":"mock-ckan","release_id":release_id,"ckan_dataset_id":f"mock-{release_id}","ckan_name":slug,"published_at":datetime.now(timezone.utc).isoformat()}
