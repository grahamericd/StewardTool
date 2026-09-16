import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from ...config import settings


class TestGenError(RuntimeError):
    pass


_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _segment(value, label: str) -> str:
    """Validate and encode a value before it becomes part of a TestGen URL path.

    These identifiers come from a steward-supplied mapping. Interpolated raw,
    a value containing "/../" or "?" re-pointed the request at a different
    TestGen endpoint while still carrying this server's bearer token.
    """
    text = str(value or "").strip()
    if not _SEGMENT_PATTERN.match(text):
        raise TestGenError(
            f"{label} must be 1-128 characters using letters, digits, dot, underscore or hyphen."
        )
    return quote(text, safe="")


class TestGenClient:
    """
    DataKitchen TestGen REST client aligned to TestGen 5.92.x.

    Confirmed live API contract:
      POST /api/v1/table-groups/{table_group_id}/profiling-runs
      GET  /api/v1/profiling-runs/{job_id}
      GET  /api/v1/profiling-runs/{job_id}/columns
      GET  /api/v1/profiling-runs/{job_id}/hygiene-issues
      GET  /api/v1/profiling-runs/{job_id}/potential-pii

      POST /api/v1/test-suites/{test_suite_id}/test-runs
      GET  /api/v1/test-runs/{job_id}
      GET  /api/v1/test-runs/{job_id}/results

    Job submission returns:
      {"id": "<uuid>", "created_at": "<timestamp>"}

    There is intentionally NO dependency on /api/v1/jobs/{job_id}.
    """

    SUCCESS_STATUSES = {
        "completed", "complete", "succeeded", "success", "finished"
    }
    FAILURE_STATUSES = {
        "error", "failed", "failure", "canceled", "cancelled", "aborted"
    }

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        auth_mode: str | None = None,
    ):
        self.base_url = (base_url or settings.testgen_base_url or "").rstrip("/")
        self.static_token = token or settings.testgen_token
        self.auth_mode = (
            auth_mode or settings.testgen_auth_mode or "oauth_refresh"
        ).lower()
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

        # Some OAuth servers rotate the refresh token. Keep the newest value
        # in process memory for the lifetime of this backend process.
        self._refresh_token = settings.testgen_oauth_refresh_token

        if not self.base_url:
            raise TestGenError("TESTGEN_BASE_URL is required in real mode.")

    def _oauth_access_token(self) -> str:
        if (
            self._access_token
            and time.time() < self._access_token_expires_at - 60
        ):
            return self._access_token

        client_id = settings.testgen_oauth_client_id
        client_secret = settings.testgen_oauth_client_secret
        refresh_token = self._refresh_token

        missing = [
            name
            for name, value in (
                ("TESTGEN_OAUTH_CLIENT_ID", client_id),
                ("TESTGEN_OAUTH_CLIENT_SECRET", client_secret),
                ("TESTGEN_OAUTH_REFRESH_TOKEN", refresh_token),
            )
            if not value
        ]
        if missing:
            raise TestGenError(
                "Missing TestGen OAuth settings: " + ", ".join(missing)
            )

        try:
            with httpx.Client(
                timeout=settings.testgen_timeout_seconds
            ) as client:
                response = client.post(
                    f"{self.base_url}/oauth/token",
                    auth=(client_id, client_secret),
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    headers={"Accept": "application/json"},
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise TestGenError(
                f"Could not refresh TestGen OAuth token: {exc}"
            ) from exc

        token = payload.get("access_token")
        if not token:
            raise TestGenError(
                "TestGen OAuth response did not include access_token."
            )

        self._access_token = token
        self._access_token_expires_at = (
            time.time() + int(payload.get("expires_in") or 3600)
        )

        rotated = payload.get("refresh_token")
        if rotated:
            self._refresh_token = rotated

        return token

    def _token(self) -> str:
        if self.auth_mode == "bearer":
            if not self.static_token:
                raise TestGenError(
                    "TESTGEN_AUTH_MODE=bearer requires TESTGEN_TOKEN."
                )
            return self.static_token

        if self.auth_mode == "oauth_refresh":
            return self._oauth_access_token()

        raise TestGenError(
            "TESTGEN_AUTH_MODE must be bearer or oauth_refresh."
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token()}",
        }

    def _request(
        self, method: str, path: str, **kwargs
    ) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=settings.testgen_timeout_seconds
            ) as client:
                response = client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    **kwargs,
                )
            response.raise_for_status()
            return response.json() if response.content else {}
        except TestGenError:
            raise
        except Exception as exc:
            raise TestGenError(
                f"TestGen request failed: {exc}"
            ) from exc

    def check_connection(self, project_code: str) -> dict:
        if not project_code:
            raise TestGenError("A TestGen project code is required.")

        result = self._request(
            "GET",
            f"/api/v1/projects/{_segment(project_code, 'TestGen project code')}/jobs",
        )
        return {
            "ok": True,
            "project_code": project_code,
            "response_type": type(result).__name__,
        }

    def submit_profile(self, table_group_id: str) -> dict:
        return self._request(
            "POST",
            f"/api/v1/table-groups/{_segment(table_group_id, 'TestGen table group id')}/profiling-runs",
        )

    def get_profile_run(self, job_id: str) -> dict:
        return self._request(
            "GET",
            f"/api/v1/profiling-runs/{_segment(job_id, 'TestGen job id')}",
        )

    def get_profile_columns(self, job_id: str) -> dict:
        return self._request(
            "GET",
            f"/api/v1/profiling-runs/{_segment(job_id, 'TestGen job id')}/columns",
        )

    def get_hygiene_issues(self, job_id: str) -> dict:
        return self._request(
            "GET",
            f"/api/v1/profiling-runs/{_segment(job_id, 'TestGen job id')}/hygiene-issues",
        )

    def get_potential_pii(self, job_id: str) -> dict:
        return self._request(
            "GET",
            f"/api/v1/profiling-runs/{_segment(job_id, 'TestGen job id')}/potential-pii",
        )

    def submit_test_run(self, test_suite_id: str) -> dict:
        return self._request(
            "POST",
            f"/api/v1/test-suites/{_segment(test_suite_id, 'TestGen test suite id')}/test-runs",
        )

    def get_test_run(self, job_id: str) -> dict:
        return self._request(
            "GET",
            f"/api/v1/test-runs/{_segment(job_id, 'TestGen job id')}",
        )

    def get_test_results(self, job_id: str) -> dict:
        return self._request(
            "GET",
            f"/api/v1/test-runs/{_segment(job_id, 'TestGen job id')}/results",
        )

    def _status(self, payload: dict) -> str:
        raw = payload.get("status")
        if isinstance(raw, dict):
            raw = (
                raw.get("value")
                or raw.get("name")
                or raw.get("status")
            )
        return str(raw or "").strip().lower()

    def _wait(self, getter, job_id: str, label: str) -> dict:
        deadline = time.time() + settings.testgen_max_wait_seconds

        while time.time() < deadline:
            run = getter(job_id)
            status = self._status(run)

            if status in self.SUCCESS_STATUSES:
                return run

            # TestGen 5.92 response includes completed_at/result as well.
            if run.get("completed_at") and status not in self.FAILURE_STATUSES:
                return run

            if status in self.FAILURE_STATUSES:
                message = (
                    run.get("error_message")
                    or run.get("message")
                    or f"TestGen {label} ended with {status}."
                )
                raise TestGenError(message)

            time.sleep(settings.testgen_poll_seconds)

        raise TestGenError(
            f"Timed out after {settings.testgen_max_wait_seconds}s "
            f"waiting for TestGen {label} {job_id}."
        )

    def wait_for_profile(self, job_id: str) -> dict:
        return self._wait(
            self.get_profile_run,
            job_id,
            "profiling run",
        )

    def wait_for_test_run(self, job_id: str) -> dict:
        return self._wait(
            self.get_test_run,
            job_id,
            "test run",
        )


class MockTestGenClient:
    def profile(self, table_name: str | None = None) -> dict:
        return {
            "id": "mock-profile-001",
            "status": "completed",
            "result": {
                "score": 0.914,
                "table_ct": 1,
                "column_ct": 24,
                "record_ct": 125440,
                "issue_counts": {
                    "hygiene_issues": {
                        "definite": 1,
                        "likely": 2,
                        "possible": 4,
                    }
                },
            },
            "suggested_expectations": [
                {
                    "name": "Application ID is required",
                    "rule_type": "not_null",
                    "plain_language_rule":
                        "Every application should have an Application ID.",
                    "definition": {
                        "type": "not_null",
                        "column": "application_id",
                    },
                },
                {
                    "name": "ZIP Code follows an expected format",
                    "rule_type": "pattern",
                    "plain_language_rule":
                        "ZIP Code should use a recognized 5-digit "
                        "or ZIP+4 format.",
                    "definition": {
                        "type": "pattern",
                        "column": "zip_code",
                    },
                },
                {
                    "name": "Application number is unique",
                    "rule_type": "unique",
                    "plain_language_rule":
                        "Application number should uniquely identify "
                        "one application.",
                    "definition": {
                        "type": "unique",
                        "column": "application_number",
                    },
                },
            ],
        }

    def run_tests(self) -> dict:
        return {
            "id": "mock-test-run-001",
            "status": "completed",
            "result": {
                "score": 0.881,
                "result_counts": {
                    "passed": 17,
                    "failed": 2,
                    "warning": 1,
                    "error": 0,
                },
            },
            "failures": [
                {
                    "rule_name":
                        "ZIP Code follows an expected format",
                    "failed_count": 1482,
                    "evaluated_count": 125440,
                    "score": 98.82,
                    "description":
                        "1,482 records do not match the approved "
                        "ZIP Code expectation.",
                    "sample_values":
                        ["3230", "FL 32301", "32301-"],
                },
                {
                    "rule_name": "Application ID is required",
                    "failed_count": 248,
                    "evaluated_count": 125440,
                    "score": 99.80,
                    "description":
                        "248 application records are missing "
                        "an Application ID.",
                    "sample_values": [None, None, None],
                },
            ],
        }
