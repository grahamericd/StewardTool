import time
from typing import Any

import httpx

from ...config import settings


class TestGenError(RuntimeError):
    pass


class TestGenClient:
    """Small REST adapter around the stable TestGen run workflow.

    Stage 3 intentionally depends only on documented endpoints for submitting
    profiling/test jobs, polling jobs, and fetching run summaries.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or settings.testgen_base_url or '').rstrip('/')
        self.token = token or settings.testgen_token
        if not self.base_url:
            raise TestGenError('TESTGEN_BASE_URL is required in real mode.')

    def _headers(self):
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=settings.testgen_timeout_seconds) as client:
                response = client.request(method, f'{self.base_url}{path}', headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except Exception as exc:
            raise TestGenError(f'TestGen request failed: {exc}') from exc

    def submit_profile(self, table_group_id: str) -> dict:
        return self._request('POST', f'/api/v1/table-groups/{table_group_id}/profiling-runs')

    def submit_test_run(self, test_suite_id: str) -> dict:
        return self._request('POST', f'/api/v1/test-suites/{test_suite_id}/test-runs')

    def get_job(self, job_id: str) -> dict:
        return self._request('GET', f'/api/v1/jobs/{job_id}')

    def get_profile_run(self, run_id: str) -> dict:
        return self._request('GET', f'/api/v1/profiling-runs/{run_id}')

    def get_test_run(self, run_id: str) -> dict:
        return self._request('GET', f'/api/v1/test-runs/{run_id}')

    def wait_for_job(self, job_id: str) -> dict:
        deadline = time.time() + settings.testgen_max_wait_seconds
        while time.time() < deadline:
            job = self.get_job(job_id)
            status = job.get('status')
            if status == 'completed':
                return job
            if status in {'error', 'canceled'}:
                raise TestGenError(job.get('error_message') or f'TestGen job ended with {status}.')
            time.sleep(settings.testgen_poll_seconds)
        raise TestGenError('Timed out waiting for TestGen job to finish.')


class MockTestGenClient:
    """Deterministic TestGen-shaped demo used until a real TestGen instance is linked."""

    def profile(self, table_name: str | None = None) -> dict:
        return {
            'id': 'mock-profile-001',
            'status': 'completed',
            'result': {
                'score': 0.914,
                'table_ct': 1,
                'column_ct': 24,
                'record_ct': 125440,
                'issue_counts': {
                    'hygiene_issues': {'definite': 1, 'likely': 2, 'possible': 4},
                    'potential_pii': {'high': 1, 'moderate': 2},
                    'dismissed': 0,
                },
            },
            'suggested_expectations': [
                {
                    'name': 'Application ID is required',
                    'rule_type': 'not_null',
                    'plain_language_rule': 'Every application should have an Application ID.',
                    'definition': {'type': 'not_null', 'column': 'application_id'},
                },
                {
                    'name': 'ZIP Code follows an expected format',
                    'rule_type': 'pattern',
                    'plain_language_rule': 'ZIP Code should use a recognized 5-digit or ZIP+4 format.',
                    'definition': {'type': 'pattern', 'column': 'zip_code'},
                },
                {
                    'name': 'Application number is unique',
                    'rule_type': 'unique',
                    'plain_language_rule': 'Application number should uniquely identify one application.',
                    'definition': {'type': 'unique', 'column': 'application_number'},
                },
            ],
        }

    def run_tests(self) -> dict:
        return {
            'id': 'mock-test-run-001',
            'status': 'completed',
            'result': {
                'score': 0.881,
                'result_counts': {'passed': 17, 'failed': 2, 'warning': 1, 'error': 0, 'log': 0, 'dismissed': 0},
            },
            'failures': [
                {
                    'rule_name': 'ZIP Code follows an expected format',
                    'failed_count': 1482,
                    'evaluated_count': 125440,
                    'score': 98.82,
                    'description': '1,482 records do not match the approved ZIP Code expectation.',
                    'sample_values': ['3230', 'FL 32301', '32301-'],
                },
                {
                    'rule_name': 'Application ID is required',
                    'failed_count': 248,
                    'evaluated_count': 125440,
                    'score': 99.80,
                    'description': '248 application records are missing an Application ID.',
                    'sample_values': [None, None, None],
                },
            ],
        }
