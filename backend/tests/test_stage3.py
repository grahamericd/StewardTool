import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["DATABASE_URL"] = "sqlite:///./test_stage3.db"
os.environ["AUTH_MODE"] = "demo"
os.environ["CATALOG_PUBLISHER"] = "mock"
os.environ["TESTGEN_MODE"] = "mock"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}


def _asset_and_resource():
    assets = client.get('/api/assets', headers=STEWARD).json()
    asset = assets[0]
    structured = next(r for r in asset['resources'] if r['structure_type'] == 'STRUCTURED')
    return asset['asset']['asset_id'], structured['resource_id']


def test_testgen_mock_status():
    with client:
        r = client.get('/api/quality/engine/status', headers=STEWARD)
        assert r.status_code == 200
        assert r.json()['provider'] == 'TESTGEN'
        assert r.json()['mode'] == 'mock'


def test_profile_generates_quality_workflow():
    with client:
        aid, rid = _asset_and_resource()
        r = client.post(f'/api/assets/{aid}/quality/assess', headers=STEWARD, json={'resource_id': rid})
        assert r.status_code == 200, r.text
        quality = client.get(f'/api/assets/{aid}/quality', headers=STEWARD).json()
        assert quality['profiles']
        assert any(rule['status'] == 'PROPOSED' for rule in quality['rules'])
        assert quality['issues']
        tasks = client.get('/api/tasks', headers=STEWARD).json()
        assert any(t['source_type'] == 'QUALITY_ISSUE' for t in tasks)


def test_approved_rule_run_creates_issue_and_decision_resolves_it():
    with client:
        aid, rid = _asset_and_resource()
        client.post(f'/api/assets/{aid}/quality/assess', headers=STEWARD, json={'resource_id': rid})
        quality = client.get(f'/api/assets/{aid}/quality', headers=STEWARD).json()
        proposed = next(r for r in quality['rules'] if r['status'] == 'PROPOSED')
        ok = client.patch(f"/api/quality/rules/{proposed['id']}/status", headers=STEWARD, json={'status':'APPROVED'})
        assert ok.status_code == 200
        run = client.post(f'/api/assets/{aid}/quality/run', headers=STEWARD, json={'resource_id': rid})
        assert run.status_code == 200, run.text
        quality = client.get(f'/api/assets/{aid}/quality', headers=STEWARD).json()
        issue = next(i for i in quality['issues'] if i['status'] == 'OPEN' and i['issue_type'] == 'RULE_FAILURE')
        decision = client.post(f"/api/quality/issues/{issue['id']}/decision", headers=STEWARD, json={'decision_type':'BAD_DATA','notes':'Confirmed with source owner.'})
        assert decision.status_code == 200
        assert decision.json()['status'] == 'RESOLVED'
