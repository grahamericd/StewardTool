from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    BusinessConcept,
    BusinessFlow,
    BusinessFunction,
    DiscoverySession,
    LandscapeAssertion,
    LandscapeEvidence,
    LandscapeSystem,
)
from app.schemas import (
    BusinessConceptCreate,
    BusinessFlowCreate,
    BusinessFunctionCreate,
    DiscoverySessionCreate,
    LandscapeAssertionCreate,
    LandscapeEvidenceCreate,
    LandscapeSystemCreate,
)

client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}
APPROVER = {"X-User-Email": "approver@demo.gov"}


def test_landscape_foundation_models_are_available():
    assert BusinessFunction.__tablename__ == "business_functions"
    assert BusinessConcept.__tablename__ == "business_concepts"
    assert BusinessFlow.__tablename__ == "business_flows"
    assert LandscapeSystem.__tablename__ == "landscape_systems"
    assert LandscapeEvidence.__tablename__ == "landscape_evidence"
    assert LandscapeAssertion.__tablename__ == "landscape_assertions"
    assert DiscoverySession.__tablename__ == "discovery_sessions"


def test_landscape_foundation_schema_payloads_validate():
    function = BusinessFunctionCreate(name="Licensing", description="Handle license applications")
    concept = BusinessConceptCreate(name="Professional License", description="An approved permit to practice")
    flow = BusinessFlowCreate(name="Application intake", description="Capture incoming applications")
    system = LandscapeSystemCreate(name="Business Licensing System", business_purpose="Manage professional licenses")
    evidence = LandscapeEvidenceCreate(
        entity_type="BusinessFunction",
        evidence_type="screening",
        summary="The report was used in review",
    )
    assertion = LandscapeAssertionCreate(
        entity_type="BusinessFunction",
        assertion_type="business_context",
        statement="Licensing applications are reviewed weekly",
    )
    session = DiscoverySessionCreate(title="Initial discovery", status="ACTIVE")

    assert function.name == "Licensing"
    assert concept.name == "Professional License"
    assert flow.name == "Application intake"
    assert system.name == "Business Licensing System"
    assert evidence.entity_type == "BusinessFunction"
    assert evidence.evidence_type == "screening"
    assert assertion.entity_type == "BusinessFunction"
    assert assertion.statement.startswith("Licensing applications")
    assert session.title == "Initial discovery"


def test_landscape_shared_domain_endpoints_work():
    with client:
        function = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Licensing", "description": "Handle license applications"},
        )
        assert function.status_code == 200
        function_id = function.json()["id"]
        assert function.json()["name"] == "Licensing"

        concept = client.post(
            "/api/landscape/concepts",
            headers=STEWARD,
            json={"name": "Professional License", "description": "Approved permit to practice"},
        )
        assert concept.status_code == 200
        assert concept.json()["name"] == "Professional License"

        flow = client.post(
            "/api/landscape/processes",
            headers=STEWARD,
            json={"name": "Application intake", "description": "Capture incoming applications"},
        )
        assert flow.status_code == 200
        assert flow.json()["name"] == "Application intake"

        system = client.post(
            "/api/landscape/systems",
            headers=STEWARD,
            json={"name": "Business Licensing System", "business_purpose": "Manage professional licenses"},
        )
        assert system.status_code == 200
        assert system.json()["name"] == "Business Licensing System"

        listing = client.get("/api/landscape/functions", headers=STEWARD)
        assert listing.status_code == 200
        assert any(item["id"] == function_id for item in listing.json())


def test_discovery_session_summary_tracks_landscape_progress():
    with client:
        session = client.post(
            "/api/discovery/sessions",
            headers=STEWARD,
            json={"title": "Licensing review", "summary": "Review the current business context"},
        )
        assert session.status_code == 200
        session_id = session.json()["id"]

        client.post(
            f"/api/discovery/sessions/{session_id}/evidence",
            headers=STEWARD,
            json={
                "entity_type": "BusinessFunction",
                "entity_id": 1,
                "evidence_type": "screening",
                "summary": "The intake report shows weekly volume.",
                "details": {"source": "business interview"},
            },
        )
        client.post(
            f"/api/discovery/sessions/{session_id}/assertions",
            headers=STEWARD,
            json={
                "entity_type": "BusinessFunction",
                "entity_id": 1,
                "assertion_type": "business_context",
                "statement": "The licensing process is reviewed weekly.",
                "confidence": 0.84,
            },
        )

        summary = client.get(f"/api/discovery/sessions/{session_id}/summary", headers=STEWARD)
        assert summary.status_code == 200
        payload = summary.json()
        assert payload["id"] == session_id
        assert payload["evidence_count"] >= 1
        assert payload["assertion_count"] >= 1


def test_landscape_records_can_be_updated_in_place():
    with client:
        created = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Permitting", "description": "Initial draft"},
        )
        assert created.status_code == 200
        function_id = created.json()["id"]

        updated = client.patch(
            f"/api/landscape/functions/{function_id}",
            headers=STEWARD,
            json={"name": "Permit processing", "description": "Handles permit review and approval", "status": "ACTIVE"},
        )
        assert updated.status_code == 200
        payload = updated.json()
        assert payload["name"] == "Permit processing"
        assert payload["description"] == "Handles permit review and approval"

        listing = client.get("/api/landscape/functions", headers=STEWARD)
        assert listing.status_code == 200
        assert any(item["id"] == function_id and item["name"] == "Permit processing" for item in listing.json())


def test_business_units_mappings_and_business_record_crud():
    with client:
        unit = client.post(
            "/api/landscape/units",
            headers=STEWARD,
            json={"name": "Business Unit CRUD Test", "unit_type": "DIVISION", "description": "Owns a business capability"},
        )
        assert unit.status_code == 200
        unit_id = unit.json()["id"]
        assert unit.json()["unit_type"] == "DIVISION"

        updated_unit = client.patch(
            f"/api/landscape/units/{unit_id}",
            headers=STEWARD,
            json={"name": "Business Unit CRUD Test Updated"},
        )
        assert updated_unit.status_code == 200
        assert updated_unit.json()["name"].endswith("Updated")

        function = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Business Function Mapping Test", "purpose": "Support a defined business outcome"},
        )
        assert function.status_code == 200
        function_id = function.json()["id"]

        mapping = client.post(
            "/api/landscape/function-unit-mappings",
            headers=STEWARD,
            json={"function_id": function_id, "unit_id": unit_id},
        )
        assert mapping.status_code == 200
        mapping_id = mapping.json()["id"]
        assert mapping.json()["function_id"] == function_id

        duplicate = client.post(
            "/api/landscape/function-unit-mappings",
            headers=STEWARD,
            json={"function_id": function_id, "unit_id": unit_id},
        )
        assert duplicate.status_code == 409

        listed_mappings = client.get("/api/landscape/function-unit-mappings", headers=STEWARD)
        assert any(item["id"] == mapping_id for item in listed_mappings.json())

        concept = client.post(
            "/api/landscape/concepts",
            headers=STEWARD,
            json={"name": "Business Concept Delete Test", "definition": "A shared business term"},
        )
        process = client.post(
            "/api/landscape/flows",
            headers=STEWARD,
            json={"name": "Business Process Delete Test", "source_function_id": function_id},
        )
        assert concept.status_code == 200
        assert process.status_code == 200
        listed_processes = client.get("/api/landscape/processes", headers=STEWARD)
        assert any(item["id"] == process.json()["id"] for item in listed_processes.json())
        legacy_flows = client.get("/api/landscape/flows", headers=STEWARD)
        assert any(item["id"] == process.json()["id"] for item in legacy_flows.json())

        assert client.delete(f"/api/landscape/function-unit-mappings/{mapping_id}", headers=STEWARD).status_code == 200
        assert client.delete(f"/api/landscape/functions/{function_id}", headers=STEWARD).status_code == 200
        assert client.delete(f"/api/landscape/concepts/{concept.json()['id']}", headers=STEWARD).status_code == 200
        assert client.delete(f"/api/landscape/processes/{process.json()['id']}", headers=STEWARD).status_code == 200
        assert client.delete(f"/api/landscape/units/{unit_id}", headers=STEWARD).status_code == 200


def test_system_inventory_tracks_category_and_partial_knowledge():
    with client:
        created = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={
                "name": "System Inventory Repository Test",
                "system_type": "REPOSITORY",
                "knowledge_status": "PARTIAL",
                "known_details": "The team uses it for source code; owner and hosting are unknown.",
                "business_purpose": "Maintain business application source code",
            },
        )
        assert created.status_code == 200
        item = created.json()
        assert item["system_type"] == "REPOSITORY"
        assert item["knowledge_status"] == "PARTIAL"
        assert item["known_details"].startswith("The team uses it")

        systems = client.get("/api/systems", headers=STEWARD)
        assert any(system["id"] == item["system_id"] for system in systems.json())

        updated = client.patch(
            f"/api/system-inventory/{item['system_id']}",
            headers=STEWARD,
            json={"knowledge_status": "CONFIRMED", "system_owner": "Platform Engineering"},
        )
        assert updated.status_code == 200
        assert updated.json()["knowledge_status"] == "CONFIRMED"
        assert updated.json()["system_owner"] == "Platform Engineering"

        inventory = client.get("/api/system-inventory", headers=STEWARD)
        assert any(record["system_id"] == item["system_id"] for record in inventory.json())
        assert any(record["knowledge_status"] == "UNASSESSED" for record in inventory.json())

        invalid = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={"name": "Invalid Inventory State", "knowledge_status": "GUESSED"},
        )
        assert invalid.status_code == 422


def test_system_inventory_delete_detaches_resources_without_deleting_them():
    with client:
        system = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={"name": "System Inventory Delete Test", "system_type": "APPLICATION"},
        )
        assert system.status_code == 200
        assets = client.get("/api/assets", headers=STEWARD).json()
        assert assets
        asset_id = assets[0]["asset"]["asset_id"]
        resource = client.post(
            f"/api/assets/{asset_id}/resources",
            headers=STEWARD,
            json={
                "system_id": system.json()["system_id"],
                "name": "System Inventory Delete Resource",
                "resource_type": "REPORT",
                "structure_type": "STRUCTURED",
            },
        )
        assert resource.status_code == 200

        deleted = client.delete(f"/api/system-inventory/{system.json()['system_id']}", headers=STEWARD)
        assert deleted.status_code == 200
        inventory = client.get("/api/system-inventory", headers=STEWARD).json()
        assert all(item["system_id"] != system.json()["system_id"] for item in inventory)
        asset_after_delete = client.get(f"/api/assets/{asset_id}", headers=STEWARD).json()
        resource_after_delete = next(item for item in asset_after_delete["resources"] if item["name"] == "System Inventory Delete Resource")
        assert resource_after_delete["system"] is None


def test_relationship_builder_validates_and_persists_typed_edges():
    with client:
        function_a = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Relationship Flow A", "purpose": "Receive a work item"},
        )
        function_b = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Relationship Flow B", "purpose": "Complete a work item"},
        )
        concept = client.post(
            "/api/landscape/concepts",
            headers=STEWARD,
            json={"name": "Relationship Concept", "definition": "A shared term"},
        )
        asset = client.post(
            "/api/assets",
            headers=STEWARD,
            json={"name": "Relationship Asset", "business_definition": "A relationship test asset"},
        )
        systems = client.get("/api/systems", headers=STEWARD).json()
        assert function_a.status_code == function_b.status_code == concept.status_code == asset.status_code == 200
        asset_id = asset.json()["asset"]["asset_id"]

        supports = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function_a.json()["id"],
                "target_type": "SYSTEM",
                "target_id": systems[0]["id"],
                "relationship_type": "SUPPORTS",
            },
        )
        assert supports.status_code == 200
        assert supports.json()["relationship_type"] == "SUPPORTS"

        duplicate = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function_a.json()["id"],
                "target_type": "SYSTEM",
                "target_id": systems[0]["id"],
                "relationship_type": "SUPPORTS",
            },
        )
        assert duplicate.status_code == 409

        concept_link = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_CONCEPT",
                "source_id": concept.json()["id"],
                "target_type": "ASSET",
                "target_id": asset_id,
                "relationship_type": "DESCRIBES",
            },
        )
        assert concept_link.status_code == 200

        owner_link = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "ASSET",
                "source_id": asset_id,
                "target_type": "PERSON",
                "relationship_type": "OWNER",
                "details": {"display_name": "Riley Owner"},
            },
        )
        assert owner_link.status_code == 200
        refreshed_asset = client.get(f"/api/assets/{asset_id}", headers=STEWARD).json()
        assert refreshed_asset["asset"]["business_owner"] == "Riley Owner"

        resource = client.post(
            f"/api/assets/{asset_id}/resources",
            headers=STEWARD,
            json={
                "name": "Relationship Resource",
                "resource_type": "REPORT",
                "structure_type": "STRUCTURED",
            },
        )
        assert resource.status_code == 200
        resource_id = resource.json()["resources"][-1]["resource_id"]
        system_resource = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "SYSTEM",
                "source_id": systems[0]["id"],
                "target_type": "RESOURCE",
                "target_id": resource_id,
                "relationship_type": "REPRESENTS",
            },
        )
        assert system_resource.status_code == 200
        linked_asset = client.get(f"/api/assets/{asset_id}", headers=STEWARD).json()
        linked_resource = next(item for item in linked_asset["resources"] if item["resource_id"] == resource_id)
        assert linked_resource["system"] == systems[0]["name"]

        dependency = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function_a.json()["id"],
                "target_type": "BUSINESS_FUNCTION",
                "target_id": function_b.json()["id"],
                "relationship_type": "DEPENDS_ON",
            },
        )
        assert dependency.status_code == 200
        cycle = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function_b.json()["id"],
                "target_type": "BUSINESS_FUNCTION",
                "target_id": function_a.json()["id"],
                "relationship_type": "DEPENDS_ON",
            },
        )
        assert cycle.status_code == 409

        process = client.post(
            "/api/landscape/processes",
            headers=STEWARD,
            json={"name": "Relationship process"},
        )
        process_flow = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function_a.json()["id"],
                "target_type": "BUSINESS_FUNCTION",
                "target_id": function_b.json()["id"],
                "relationship_type": "PROCESS_FLOW",
                "process_id": process.json()["id"],
            },
        )
        assert process_flow.status_code == 200
        assert any(
            relationship["id"] == f"legacy:process-flow:{process.json()['id']}"
            for relationship in client.get("/api/landscape/relationships", headers=STEWARD).json()
        )

        invalid = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": 999999,
                "target_type": "SYSTEM",
                "target_id": systems[0]["id"],
                "relationship_type": "SUPPORTS",
            },
        )
        assert invalid.status_code == 404
        malformed_delete = client.delete(
            "/api/landscape/relationships/legacy:system-resource:not-an-id:also-not-an-id",
            headers=STEWARD,
        )
        assert malformed_delete.status_code == 404
        assert client.delete(f"/api/landscape/relationships/{system_resource.json()['id']}", headers=STEWARD).status_code == 200


def test_landscape_completion_reports_gaps_duplicates_and_readiness():
    with client:
        function = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Completion Check Function"},
        )
        system = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={"name": "Completion Check Unconnected System", "system_type": "APPLICATION"},
        )
        concept_one = client.post(
            "/api/landscape/concepts",
            headers=STEWARD,
            json={"name": " Completion Check Term ", "definition": "First definition"},
        )
        concept_two = client.post(
            "/api/landscape/concepts",
            headers=STEWARD,
            json={"name": "completion   check term", "definition": "Alternate definition"},
        )
        assert function.status_code == system.status_code == concept_one.status_code == concept_two.status_code == 200

        completion = client.get("/api/landscape/completion", headers=STEWARD)
        assert completion.status_code == 200
        initial = completion.json()
        guidance_codes = {item["code"] for item in initial["guidance"]}
        assert initial["missing_business_functions"] is False
        assert any(item["id"] == system.json()["system_id"] for item in initial["unconnected_systems"])
        assert any(len(group["items"]) == 2 for group in initial["duplicate_concepts"])
        assert "Departments and units" in initial["empty_sections"]
        assert any(item["name"] == "Completion Check Function" for item in initial["incomplete_functions"])
        assert "EMPTY_SECTIONS" in guidance_codes
        if initial["counts"]["function_system_connections"] == 0:
            assert "NO_FUNCTION_SYSTEM_CONNECTIONS" in guidance_codes

        connected = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function.json()["id"],
                "target_type": "SYSTEM",
                "target_id": system.json()["system_id"],
                "relationship_type": "SUPPORTS",
            },
        )
        assert connected.status_code == 200
        after_connection = client.get("/api/landscape/completion", headers=STEWARD).json()
        assert after_connection["ready_to_proceed"] is True
        assert after_connection["state"] == "READY_TO_PROCEED"
        assert after_connection["completeness_score"] >= initial["completeness_score"]


def test_landscape_draft_persists_partial_state_and_restores_revision():
    with client:
        saved_draft = client.patch(
            "/api/landscape/draft",
            headers=STEWARD,
            json={"draft_data": {"active_tab": "Business functions", "form": {"name": "Partially typed function"}}},
        )
        assert saved_draft.status_code == 200
        assert saved_draft.json()["draft_data"]["form"]["name"] == "Partially typed function"

        baseline = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Draft Restore Baseline", "purpose": "Baseline business outcome"},
        )
        assert baseline.status_code == 200
        baseline_concept = client.post(
            "/api/landscape/concepts",
            headers=STEWARD,
            json={"name": "Draft Restore Concept", "definition": "Baseline concept"},
        )
        baseline_unit = client.post(
            "/api/landscape/units",
            headers=STEWARD,
            json={"name": "Draft Restore Unit"},
        )
        baseline_mapping = client.post(
            "/api/landscape/function-unit-mappings",
            headers=STEWARD,
            json={"function_id": baseline.json()["id"], "unit_id": baseline_unit.json()["id"]},
        )
        baseline_process = client.post(
            "/api/landscape/processes",
            headers=STEWARD,
            json={"name": "Draft Restore Process"},
        )
        baseline_system = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={"name": "Draft Restore System", "system_type": "REPOSITORY", "knowledge_status": "PARTIAL"},
        )
        assets = client.get("/api/assets", headers=STEWARD).json()
        asset_id = assets[0]["asset"]["asset_id"]
        baseline_resource = client.post(
            f"/api/assets/{asset_id}/resources",
            headers=STEWARD,
            json={
                "system_id": baseline_system.json()["system_id"],
                "name": "Draft Restore Resource",
                "resource_type": "REPORT",
                "structure_type": "STRUCTURED",
            },
        )
        baseline_edge = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": baseline.json()["id"],
                "target_type": "SYSTEM",
                "target_id": baseline_system.json()["system_id"],
                "relationship_type": "SUPPORTS",
            },
        )
        assert all(response.status_code == 200 for response in (baseline_concept, baseline_unit, baseline_mapping, baseline_process, baseline_system, baseline_resource, baseline_edge))
        checkpoint = client.post(
            "/api/landscape/draft/checkpoint",
            headers=STEWARD,
            json={"label": "Before removing baseline function"},
        )
        assert checkpoint.status_code == 200
        revision_id = checkpoint.json()["revision"]["id"]

        later = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Draft Restore Later Entry"},
        )
        later_system = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={"name": "Draft Restore Later System", "system_type": "APPLICATION"},
        )
        assert later.status_code == later_system.status_code == 200
        client.delete(f"/api/landscape/functions/{baseline.json()['id']}", headers=STEWARD)
        client.delete(f"/api/landscape/concepts/{baseline_concept.json()['id']}", headers=STEWARD)
        client.delete(f"/api/landscape/processes/{baseline_process.json()['id']}", headers=STEWARD)
        client.delete(f"/api/landscape/units/{baseline_unit.json()['id']}", headers=STEWARD)
        client.delete(f"/api/system-inventory/{baseline_system.json()['system_id']}", headers=STEWARD)

        draft = client.get("/api/landscape/draft", headers=STEWARD)
        assert draft.status_code == 200
        assert draft.json()["draft_data"]["form"]["name"] == "Partially typed function"
        assert any(item["id"] == revision_id for item in draft.json()["revisions"])

        restored = client.post(f"/api/landscape/draft/restore/{revision_id}", headers=STEWARD)
        assert restored.status_code == 200
        functions = client.get("/api/landscape/functions", headers=STEWARD).json()
        names = {item["name"] for item in functions}
        assert "Draft Restore Baseline" in names
        assert "Draft Restore Later Entry" not in names
        assert any(item["id"] == baseline_concept.json()["id"] for item in client.get("/api/landscape/concepts", headers=STEWARD).json())
        assert any(item["id"] == baseline_process.json()["id"] for item in client.get("/api/landscape/processes", headers=STEWARD).json())
        assert any(item["id"] == baseline_unit.json()["id"] for item in client.get("/api/landscape/units", headers=STEWARD).json())
        assert any(item["id"] == baseline_mapping.json()["id"] for item in client.get("/api/landscape/function-unit-mappings", headers=STEWARD).json())
        inventory = client.get("/api/system-inventory", headers=STEWARD).json()
        assert any(item["system_id"] == baseline_system.json()["system_id"] and item["knowledge_status"] == "PARTIAL" for item in inventory)
        assert all(item["system_id"] != later_system.json()["system_id"] for item in inventory)
        restored_asset = client.get(f"/api/assets/{asset_id}", headers=STEWARD).json()
        assert any(item["name"] == "Draft Restore Resource" and item["system"] == "Draft Restore System" for item in restored_asset["resources"])
        restored_relationships = client.get("/api/landscape/relationships", headers=STEWARD).json()
        assert any(item["id"] == baseline_edge.json()["id"] for item in restored_relationships)
        assert client.get("/api/landscape/draft", headers=STEWARD).json()["draft_data"] == {}


def test_landscape_handoff_creates_idempotent_stage_tasks_and_explicit_routes():
    with client:
        function = client.post(
            "/api/landscape/functions",
            headers=STEWARD,
            json={"name": "Handoff Core Function", "purpose": "Support the handoff workflow"},
        )
        system = client.post(
            "/api/system-inventory",
            headers=STEWARD,
            json={"name": "Handoff Core System", "system_type": "APPLICATION"},
        )
        asset = client.post(
            "/api/assets",
            headers=STEWARD,
            json={"name": "Handoff New Information", "business_definition": None},
        )
        assert function.status_code == system.status_code == asset.status_code == 200
        link = client.post(
            "/api/landscape/relationships",
            headers=STEWARD,
            json={
                "source_type": "BUSINESS_FUNCTION",
                "source_id": function.json()["id"],
                "target_type": "SYSTEM",
                "target_id": system.json()["system_id"],
                "relationship_type": "SUPPORTS",
            },
        )
        assert link.status_code == 200

        first = client.post("/api/landscape/handoff", headers=STEWARD)
        assert first.status_code == 200, first.text
        payload = first.json()
        stage_map = {stage["key"]: stage for stage in payload["stages"]}
        assert payload["success"] is True
        assert payload["created_task_ids"]
        assert stage_map["understanding"]["page"] == "Information Details"
        assert stage_map["understanding"]["tab"] == "Help Others Understand It"
        assert stage_map["understanding"]["task_count"] >= 1
        assert stage_map["official_source"]["tab"] == "Where It Lives"
        assert stage_map["quality"]["tab"] == "Can This Information Be Trusted?"
        assert payload["next_stage"]["key"] in {"understanding", "official_source", "quality", "approval"}

        task_list = client.get("/api/tasks", headers=STEWARD)
        assert task_list.status_code == 200
        assert any(task["id"] in payload["created_task_ids"] for task in task_list.json())

        second = client.post("/api/landscape/handoff", headers=STEWARD)
        assert second.status_code == 200
        assert second.json()["created_task_ids"] == []

        reviewer_handoff = client.post("/api/landscape/handoff", headers=APPROVER)
        assert reviewer_handoff.status_code == 200
        reviewer_approval = next(stage for stage in reviewer_handoff.json()["stages"] if stage["key"] == "approval")
        assert reviewer_approval["page"] == "Review Queue"


def test_approver_landscape_access_is_read_only():
    with client:
        functions = client.get("/api/landscape/functions", headers=APPROVER)
        completion = client.get("/api/landscape/completion", headers=APPROVER)
        relationships = client.get("/api/landscape/relationships", headers=APPROVER)
        assert functions.status_code == completion.status_code == relationships.status_code == 200

        assert client.post(
            "/api/landscape/functions",
            headers=APPROVER,
            json={"name": "Approvers may not construct the landscape"},
        ).status_code == 403
        assert client.post(
            "/api/system-inventory",
            headers=APPROVER,
            json={"name": "Approvers may not add systems"},
        ).status_code == 403
        assert client.patch(
            "/api/landscape/draft",
            headers=APPROVER,
            json={"draft_data": {"forbidden": True}},
        ).status_code == 403
