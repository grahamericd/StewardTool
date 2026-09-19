"""Shared test configuration.

pytest imports this before any test module, which is the only reliable moment
to configure the application: ``app.config.settings`` is a module-level
singleton, so environment variables set inside an individual test file are
ignored whenever another module imported the app first. That is why the test
suite behaved differently depending on which file ran first, and why it wrote
SQLite files into the source tree.
"""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

_TMP_DIR = tempfile.mkdtemp(prefix="ai-data-steward-tests-")
atexit.register(shutil.rmtree, _TMP_DIR, True)

os.environ.update(
    {
        "APP_ENV": "test",
        # CI also runs the suite against PostgreSQL, so an externally supplied
        # DATABASE_URL wins over the temporary SQLite file.
        "DATABASE_URL": os.environ.get("DATABASE_URL") or f"sqlite:///{_TMP_DIR}/test.db",
        "AUTH_MODE": "demo",
        "SEED_DEMO_DATA": "true",
        "CATALOG_PUBLISHER": "mock",
        "TESTGEN_MODE": "mock",
        "CORS_ORIGINS": "http://localhost:5173",
        # TestClient sends "Host: testserver", which TrustedHostMiddleware
        # rejects with 400 unless it is allowed here.
        "TRUSTED_HOSTS": "localhost,127.0.0.1,testserver",
        "AUTH_SECRET_KEY": "test-secret-key-that-is-long-enough-000000",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

STEWARD = {"X-User-Email": "steward@demo.gov"}
APPROVER = {"X-User-Email": "approver@demo.gov"}
ADMIN = {"X-User-Email": "admin@demo.gov"}


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def steward_headers():
    return dict(STEWARD)


@pytest.fixture(scope="session")
def approver_headers():
    return dict(APPROVER)


@pytest.fixture
def first_asset_id(client):
    assets = client.get("/api/assets", headers=STEWARD).json()
    assert assets, "the demo seed should provide at least one asset"
    return assets[0]["asset"]["asset_id"]
