_Independent code review_

# AI Data Steward Code Review

A second-opinion review of the self-hosted MVP (backend, frontend, deployment tooling, and tests) with findings ranked by severity, each tagged with how it was verified.

- **Repository:** StewardTool at `92c59ef` (Version 4.4h)
- **Reviewed:** 14 September 2026
- **Reviewer:** Claude (Fable 5.1), at the request of a colleague of the author
- **Scope:** All 9,300 lines of application code, scripts, compose files, and docs

## Summary

This is a genuinely thoughtful product. The steward-facing language is careful, the publication lifecycle with hashed immutable releases is a good design, the production configuration validator refuses the obvious foot-guns, and the container hardening (three networks, read-only filesystems, non-root backend, health checks, backup and restore scripts) is well beyond what most MVPs ship with. The foundation is worth building on.

The review also found problems that block a real pilot, several of which only appear off the happy path and so were probably never seen. Both endpoints that record a steward's decision on a quality issue fail on every call (one has a stray parameter, the other passes a field name the model does not have). The committed test suite fails on a fresh clone. Following the production domain guide leaves the backend container permanently unhealthy. The nightly backup unit cannot run as shipped. And the headline workflow of proposing, approving and running quality expectations exists only in the mock TestGen mode; the real integration never proposes expectations or records results. On the security side the important items are a login brute-force protection that is bypassed with one request header, any steward being able to point the shared TestGen service account at any table group, and published vulnerabilities in pinned dependencies.

None of this is unusual for a four-day build with an AI assistant. The pattern is that each stage was validated by clicking through the intended path, and this review concentrates on what happens beside it. Every finding names the file and line, and the ones that could be reproduced were.

| Critical | High | Medium | Low | Confirmed by running |
|---|---|---|---|---|
| 2 | 14 | 36 | 10 | 11 |

**Critical** means a core workflow cannot be completed; **High** blocks a pilot or crosses a trust boundary; **Medium** is wrong behaviour off the happy path or a hardening gap that matters in production; **Low** is consistency and quality. _verified by running_ means the behaviour was reproduced by executing the code during this review; _by reading_ means it was established by reading the code at the cited lines.

## 1. How the review was done

Every source file was read in full: the FastAPI backend (`backend/app`, about 4,900 lines), the React frontend (`frontend/src`, about 2,400 lines), all fourteen operator scripts, both compose files, the Caddy and nginx configuration, the systemd units, and the four guides. On top of reading, the following were executed on a clean checkout on 14 September 2026:

- The backend was started in a test harness against SQLite in demo, local, and domain-style configurations, and specific requests were sent to reproduce suspected bugs. Outputs are in the [verification log](#log).
- The committed test suite was run with the pinned dependencies (Python 3.13).
- `pip-audit` was run against `backend/requirements.txt` and `npm audit` against the frontend lockfile.
- The frontend production build was run with `npm ci` and `vite build`.
- Git history was scanned for committed secrets and for sensitive files that were ever tracked. None were found.

The review did not run TestGen or CKAN, so findings about the real integration modes are from reading the client code and the documented TestGen API contract. Nothing in the repository was modified.

## 2. Fix these first

In this order. The first six are each under a day; together they make the difference between a demo and a pilot.

1. **Fix both quality-decision endpoints** ([BUG-01](#bug-01), [ORCH-01](#orch-01)). Delete the stray parameter in one; rename `actor_id` to `decided_by` in the other. Two one-line changes, then a test for each.
2. **Get the test suite green**: make timestamps comparable regardless of database ([BUG-02](#bug-02)) and fix the finding-name regression ([ORCH-02](#orch-02)). Then add a workflow that runs it on every push ([OPS-08](#ops-08)).
3. **Fix the production health check** so the domain guide produces a running stack ([BUG-03](#bug-03)).
4. **Make the backup unit runnable and the restore safe** ([OPS-02](#ops-02), [OPS-03](#ops-03)). As shipped there is no nightly backup, and a failed restore leaves no database and no running services.
5. **Close the login throttle bypass** ([SEC-01](#sec-01)) and **stop accepting arbitrary TestGen identifiers** from stewards ([SEC-03](#sec-03), [SEC-10](#sec-10)).
6. **Upgrade PyJWT and FastAPI/Starlette** and add `pip-audit` to CI ([SEC-02](#sec-02)).
7. **Adopt Alembic before the first pilot database exists** ([OPS-01](#ops-01)). Retrofitting migrations onto a live database is far more painful than starting with them.
8. **Make the frontend report failures honestly**: have the shared action helper return success or failure, disable buttons while a request is in flight, and add an error boundary ([FE-01](#fe-01), [FE-04](#fe-04), [FE-05](#fe-05)).
9. **Move TestGen runs to a background job** with a status endpoint the UI polls ([BUG-09](#bug-09)). Any real profiling run longer than a minute currently fails at the proxy.
10. **Decide what real TestGen mode is supposed to do** about expectations and results ([ORCH-03](#orch-03)). Until then the README describes the mock.
11. **Add an audit log** for sign-ins and administrative actions ([SEC-07](#sec-07)). For a government stewardship tool this will be asked for.
12. **Split the three large files** along the lines suggested in [section 8](#quality) and add a formatter and linter, so the next round of changes is reviewable.

## 3. Security

The authentication design is fundamentally sound: scrypt with a constant-time compare, signed tokens with issuer, audience and expiry, and the local mode correctly ignores the demo identity header. The findings below are about the edges of that design.

<a id="sec-01"></a>
#### SEC-01 — Login brute-force protection can be bypassed with a request header

**Severity:** High · **Evidence:** verified by running

The throttle key is built from the *first* value in `X-Forwarded-For` (`backend/app/api/auth_routes.py:20-23`). Both Caddy and nginx *append* the real client address to whatever the client already sent, so the first value is attacker-controlled in the deployed topology too. Sending a different address on each attempt produced eight consecutive 401s against one account with the limit set to three; no 429 was ever returned. The counter is also held in process memory, so it resets on restart and is not shared between workers, and there is no per-account lockout, so a distributed attacker is never slowed down.

**Fix:** stop parsing the header yourself. Set uvicorn's `--forwarded-allow-ips` to the frontend container's network rather than `*` and use `request.client.host`; add a per-account failure counter stored in the database (or Redis) with a lockout and an audit event; consider a small delay on failure. The in-memory dictionary also grows by one entry per address and account and is pruned only when the same key is touched again, so it is a slow memory leak under a scan.

<a id="sec-02"></a>
#### SEC-02 — Pinned dependencies have published vulnerabilities

**Severity:** High · **Evidence:** verified by running

`pip-audit` reports seven advisories against PyJWT 2.10.1 (fixed in 2.13.0) and six against Starlette 0.47.3, which is what FastAPI 0.116.1 pulls in (fixed across 0.49.1 to 1.3.1). PyJWT is the library that validates every session token. The frontend lockfile is clean.

**Fix:** bump PyJWT to 2.13 or later and FastAPI to a release that requires Starlette 1.3.1 or later, re-run the suite, and add `pip-audit` and `npm audit` to CI. Also drop `pytest` from `requirements.txt` in the production image; it has its own advisory and does not belong there.

<a id="sec-03"></a>
#### SEC-03 — Any steward can point the shared TestGen account at any table group

**Severity:** High · **Evidence:** by reading

TestGen is reached with one service credential for the whole deployment (`config.py:44-53`), and the link payload lets any STEWARD set `project_code`, `table_group_id` and `test_suite_id` to any value (`schemas.py:102-115`). Nothing maps an organisation to the TestGen projects it is allowed to see. `assess_resource` then profiles whatever table group was typed and stores the hygiene findings, column profiles and potential-PII samples into the caller's organisation (`quality_orchestrator.py:1491, 1253-1257`), where `GET /quality` serves them back. In a multi-organisation deployment this is a cross-tenant read of another agency's data through the quality engine. The default table group from the environment is also shared by every organisation (`quality_orchestrator.py:26-34`).

**Fix:** store the allowed TestGen project codes per organisation and validate every link against them; restrict link editing to ORG_ADMIN; treat the stored profile details as data of the organisation that owns the source, not the one that requested the run.

<a id="sec-04"></a>
#### SEC-04 — OIDC audience check is optional and production does not require OIDC settings

**Severity:** Medium · **Evidence:** by reading

In OIDC mode, audience verification is disabled whenever `OIDC_AUDIENCE` is unset (`backend/app/auth.py:137`), so any valid token issued by the identity provider for any application would be accepted. The production validator in `config.py` checks local-mode settings carefully but does not require `OIDC_ISSUER` or `OIDC_AUDIENCE` when `AUTH_MODE=oidc`, and the hardening script passes the same configuration.

**Fix:** require both in production and always verify audience. Note that the frontend has no OIDC sign-in flow at all ([FE-07](#fe-07)), so this mode cannot currently be used end to end.

<a id="sec-05"></a>
#### SEC-05 — Sessions cannot be revoked

**Severity:** Medium · **Evidence:** by reading

Logout is a no-op on the server (`auth_routes.py:134-139`), and changing a password, an administrator resetting it, or changing a role does not invalidate tokens already issued. Only deactivating the account does (checked on every request in `auth.py:157-161`, which is good). With eight-hour tokens in browser storage, a compromised or shared token stays valid for the rest of the day after the password is changed. Rotating `AUTH_SECRET_KEY` is a global sign-out because there is no dual-key window.

**Fix:** include a token version or `password_changed_at` in the claims and compare on each request, or keep a server-side session table so logout and resets revoke immediately; accept a previous signing key for the token lifetime during rotation.

<a id="sec-06"></a>
#### SEC-06 — Bearer token lives in localStorage; nginx sends no security headers; no HSTS

**Severity:** Medium · **Evidence:** by reading

The token is kept in `localStorage` (`frontend/src/api.js:2-6`), which any script running on the origin can read. The Caddy edge sets a strict Content-Security-Policy, which is the right mitigation, but the nginx layer behind it sets nothing, so any path to the frontend that does not pass through Caddy (the development compose file, a future load balancer) is unprotected. Caddy also does not send `Strict-Transport-Security`. The policy's `style-src 'unsafe-inline'` is needed only by one inline style at `main.jsx:338`.

**Fix:** add HSTS to the Caddyfile once the real domain is live; duplicate the security headers in `nginx.conf` as defence in depth; add `object-src 'none'` and remove the inline style. Longer term, issue the token as an `HttpOnly; Secure; SameSite=Strict` cookie and add CSRF protection (an `Origin` check is enough for a JSON API).

<a id="sec-07"></a>
#### SEC-07 — No audit trail for sign-ins or administrative actions

**Severity:** Medium · **Evidence:** by reading

The `publication_events` table records the publication lifecycle well, but nothing records who signed in, failed to sign in, created a user, changed a role, deactivated an account, or issued a temporary password. Temporary passwords are returned in the API response with no expiry (`admin_routes.py:150, 275`). The Caddy edge has no `log` directive, so there are no access logs either.

**Fix:** add an `audit_events` table (actor, action, target, timestamp, source address) written from the auth and admin routes, expose it read-only to ORG_ADMIN, give temporary passwords a short validity window, and turn on edge access logging.

<a id="sec-08"></a>
#### SEC-08 — Demo mode is header impersonation, and the dev stack exposes it on the host

**Severity:** Medium · **Evidence:** verified by running

In demo mode any request with `X-User-Email: admin@demo.gov` is the organisation administrator; the review confirmed `/api/admin/users` returns all users with that header alone. This is by design and the production validator refuses it, which is the correct control. The residual risk is `docker-compose.yml`, which runs demo mode and publishes the backend on port 8000 and PostgreSQL on port 5433 (password `steward`) on every host interface, with `--forwarded-allow-ips=*`. A developer machine on an office network is an open administrator API and an open database, and Docker's port publishing bypasses `ufw`. The go-live network check only inspects the production project, so a dev stack on the same host passes it.

**Fix:** bind development ports to `127.0.0.1` (`"127.0.0.1:8000:8000"`, same for 5433), log a prominent warning at startup in demo mode, and make the network check look at every container on the host.

<a id="sec-09"></a>
#### SEC-09 — Input validation is thin

**Severity:** Medium · **Evidence:** verified by running

No request schema sets a maximum length, so a 300-character system name is accepted; SQLite stores it, but PostgreSQL's `String(255)` column raises and the client gets a 500. Fields that behave as enums (`structure_type`, `resource_type`, `relationship_type`, `metadata_source`, `review_status`, `source`) accept any string, and `structure_type=banana` was stored. `metadata_value` is typed `Any`; `rule_definition`, review `answers` and decision `notes` are unbounded. `review_status` on metadata is client-supplied and defaults to `APPROVED`, so a steward approves their own metadata; there is no separate metadata review flow, so this may be intended, but it should then not be a request field.

**Fix:** use `Literal` or `Enum` types and `max_length` in `schemas.py`; cap JSON payload sizes; drop client control of `review_status`.

<a id="sec-10"></a>
#### SEC-10 — TestGen identifiers are interpolated into request paths and can redirect the request

**Severity:** Medium · **Evidence:** verified by running

`project_code`, `table_group_id` and `test_suite_id` are placed directly into TestGen URL paths (`integrations/testgen/client.py:173, 184, 214`) with no pattern or length check, and httpx resolves dot segments and honours `?` and `#`. Confirmed with the pinned httpx: a table group ID of `x?limit=1#frag` turns the profiling POST into a POST to the table group itself, and `../../projects/other/jobs` reaches a different resource. This is request forgery against TestGen with the service's own bearer token, from any steward account. It compounds [SEC-03](#sec-03).

**Fix:** validate table group and test suite IDs as UUIDs and project codes against a short slug pattern, and percent-encode path segments with `quote(value, safe="")`.

<a id="sec-11"></a>
#### SEC-11 — Sample values, including potential PII, are stored verbatim and served to every role

**Severity:** Medium · **Evidence:** by reading

Profiling stores TestGen's `potential_pii` list, hygiene items and column profiles (top values, minimum and maximum, samples) into `QualityIssue.details` without redaction or size limit (`quality_orchestrator.py:806-851, 1253-1257`), and `GET /quality` returns them to every organisation member including VIEWER. For a licensing or corporate-registry table these samples are the records themselves.

**Fix:** store counts and patterns, not values, unless the column is explicitly cleared; mask samples for columns TestGen flags as PII; restrict raw evidence to steward roles.

<a id="sec-12"></a>
#### SEC-12 — Operator scripts handle secrets carelessly

**Severity:** Medium · **Evidence:** by reading

- `scripts/fresh_install.sh:56` passes the generated database password and signing key to Python as command-line arguments, visible in `ps` to every local user while it runs.
- `scripts/testgen_oauth_setup.py:47-48` prints the OAuth client secret and refresh token to the terminal (scrollback, tmux and session logs), which contradicts the "never prints secret values" stance elsewhere.
- `scripts/check_production_hardening.py:95` builds a shell command from `argv[1]` with `os.system`; a path with spaces or metacharacters is injected. The same line prints a PASS about git tracking unconditionally, including when `git` is absent.
- `scripts/install_testgen.sh:8-9` downloads an installer from an unpinned `main` branch without `-f` (an error page would be saved and run) or any checksum, and executes it.

**Fix:** pass secrets through the environment or stdin; never print them; use `subprocess.run([...])`; pin the installer to a tag and verify a checksum.

<a id="sec-13"></a>
#### SEC-13 — Minor information disclosure

**Severity:** Low · **Evidence:** verified by running

`/health` reports version, environment, auth mode and publisher to anyone. `/api/quality/engine/status` returns the TestGen base URL and object IDs to every role including VIEWER. Invalid OIDC tokens echo the library exception text (`auth.py:140`), TestGen errors echo the upstream URL (`quality_orchestrator.py:1647, 1819`), and the frontend renders server error strings verbatim, including raw validation objects.

**Fix:** reduce `/health` to status only, restrict engine status to steward roles and above, and map errors to fixed messages.

<a id="sec-14"></a>
#### SEC-14 — Role model inconsistencies and no tenant filter inside the service layer

**Severity:** Low · **Evidence:** by reading

ENTERPRISE_ADMIN can approve and publish but cannot submit (`routes.py:823`); ORG_ADMIN can do both, with separation of duties enforced only by the "submitter cannot approve" check. A user with several memberships always lands in the first one (`auth.py:176`) with no way to switch, and ENTERPRISE_ADMIN is scoped to a single organisation despite the name. Unknown e-mail addresses return from login without running scrypt, which makes account enumeration possible by timing. Inside `quality_orchestrator.py` no query filters by `organization_id`; every route guards the organisation before calling in, so this is not exploitable today, but nothing enforces it for the next caller.

**Fix:** write the role matrix down once, generate the `require_roles` lists from it, add organisation selection for multi-org users, and pass the organisation into the service functions.

## 4. Backend correctness

<a id="bug-01"></a>
#### BUG-01 — Recording a quality-issue decision always fails

**Severity:** Critical · **Evidence:** verified by running

The handler signature at `backend/app/api/routes.py:777` reads `def quality_issue_decision(issue_id: int, payload: QualityDecisionCreate, HygieneFindingDecisionCreate, ctx=...)`. The bare name `HygieneFindingDecisionCreate` is a leftover from an edit; FastAPI treats an unannotated parameter as a required query parameter, so every request the UI sends (`main.jsx:1602`, JSON body only) gets `422 {"loc":["query","HygieneFindingDecisionCreate"],"msg":"Field required"}`. The "Guided investigation" decision for failed quality checks, which the README describes as the core Stage 3 workflow, cannot be completed by any user. The separate per-finding decision endpoint fails for a different reason ([ORCH-01](#orch-01)), so no quality decision of any kind can currently be recorded.

**Fix:** delete the stray parameter. Then add a test that posts a decision.

<a id="bug-02"></a>
#### BUG-02 — Timestamps from SQLite are naive, and nearly every endpoint compares them to aware values

**Severity:** High · **Evidence:** verified by running

The models declare `DateTime(timezone=True)`, but SQLite does not store offsets, so anything reloaded from it comes back naive. The periodic-review feature introduced comparisons against `datetime.now(timezone.utc)` at `routes.py:373` and `services/task_service.py:39`; the second runs inside `sync_tasks`, which the dashboard, asset list, task list, asset detail and every mutation call. On the default `DATABASE_URL` (SQLite) every one of those endpoints returns 500 as soon as one asset exists. The committed tests configure SQLite explicitly, and six of the seven failures are this error (the seventh is [ORCH-02](#orch-02)). PostgreSQL is unaffected, which is presumably why it went unnoticed.

**Fix:** add a `TypeDecorator` for the datetime columns that attaches UTC on load, or normalise in one helper before comparing. Run the tests against PostgreSQL in CI as well as SQLite. Also note the API returns naive ISO strings on SQLite and offset-aware ones on PostgreSQL, so the contract differs by database.

<a id="bug-03"></a>
#### BUG-03 — Following the domain guide makes the backend container permanently unhealthy

**Severity:** High · **Evidence:** verified by running

`.env.domain.example` sets `TRUSTED_HOSTS=steward.example.com`. The backend's Docker health check calls `http://127.0.0.1:8000/health`, so the `Host` header is `127.0.0.1`, and `TrustedHostMiddleware` answers `400 Invalid host header`. Reproduced in the harness. Because `frontend` and `edge` both depend on `backend` being healthy, the stack never comes up after the domain change. The `.env.production.example` local values happen to include `127.0.0.1`, which is why local validation passes.

**Fix:** exempt `/health` from the host check (mount it before the middleware or handle it in the middleware), or always append `localhost,127.0.0.1` to the trusted list in code, and update the example file. Add a note to `go_live_check.sh` that verifies the container health check against the configured hosts.

<a id="bug-04"></a>
#### BUG-04 — Republishing to CKAN duplicates resources and can leave CKAN and the database out of step

**Severity:** Medium · **Evidence:** by reading

`services/publisher.py:74-88` patches the existing package and then calls `resource_create` for every resource on every publish; nothing updates or removes resources created last time, so each republish adds another copy of each distribution. The CKAN calls happen before the database commit (`publication.py:114-129`), with no retry or idempotency key, so a failure after `package_create` leaves a dataset in CKAN with no record locally, and a database failure after success leaves the reverse. CKAN tag names are not sanitised to CKAN's allowed character set.

**Fix:** store CKAN resource IDs on the release, use `resource_patch`/`resource_delete` to reconcile, and record a "publishing" state before the external call so a retry can resume.

<a id="bug-05"></a>
#### BUG-05 — Read endpoints write to the database on every request

**Severity:** Medium · **Evidence:** by reading

`GET /api/assets`, `/api/dashboard` and `/api/tasks` run `sync_tasks` (which also runs quality-issue reconciliation) and commit for every asset in the organisation on every page view; `GET /api/assets/{id}/quality` creates engine-link rows in real mode and commits enriched issue details. This is O(assets) writes per navigation, is not idempotent, and will contend under two stewards clicking at once. It also makes the list endpoint the slowest one in the API.

**Fix:** reconcile tasks when the underlying data changes (on mutation) or in a periodic job, and keep GET handlers read-only.

<a id="bug-06"></a>
#### BUG-06 — "My Next Steps" is sorted alphabetically by priority

**Severity:** Medium · **Evidence:** by reading

`routes.py:550-553` orders by the `priority` string, which yields HIGH, LOW, MEDIUM. The frontend then presents that order as "start at the top".

**Fix:** order by a `case()` mapping HIGH=0, MEDIUM=1, LOW=2, or store a numeric rank.

<a id="bug-07"></a>
#### BUG-07 — Dashboard average quality score uses an arbitrary profile

**Severity:** Medium · **Evidence:** by reading

`routes.py:193` takes `quality_profiles[0]` from a relationship with no ordering, so the "latest" score is whichever row the database returns first. `services/snapshot.py:31` sorts by `profiled_at` correctly; the dashboard should reuse it.

<a id="bug-08"></a>
#### BUG-08 — Completing a readiness task does not stick

**Severity:** Medium · **Evidence:** by reading

`POST /tasks/{id}/complete` marks any task complete, but `sync_tasks` reopens readiness-derived tasks whenever the underlying check is still incomplete (`task_service.py:95-97`), which happens on the very next request. The "Complete" control on those tasks therefore does nothing visible, without saying so.

**Fix:** hide completion for `READINESS` tasks (they complete themselves when the data is filled in), or record a steward override with a reason that `sync_tasks` respects.

<a id="bug-09"></a>
#### BUG-09 — TestGen runs block the request for up to ten minutes

**Severity:** Medium · **Evidence:** by reading

`client.py:239-266` polls synchronously inside the request handler with `TESTGEN_MAX_WAIT_SECONDS=600`. nginx's default `proxy_read_timeout` is 60 seconds, so any profiling or test run longer than that returns a 504 to the browser while the backend keeps polling, and the UI shows a failure for work that then succeeds. Sync handlers run on a threadpool of forty, so a few concurrent runs also starve the rest of the API.

**Fix:** submit the run, store a job row with the TestGen job ID, return immediately, and let a background worker (or a scheduler tick) poll and ingest results. The UI polls the job row. `FastAPI BackgroundTasks` is enough for a single-process MVP; a queue is better once there are workers.

<a id="bug-10"></a>
#### BUG-10 — Rotated OAuth refresh tokens are thrown away

**Severity:** Medium · **Evidence:** by reading

The client comments that some OAuth servers rotate the refresh token and keeps the newest one on the instance (`client.py:55-57, 118-120`), but a new `TestGenClient()` is constructed for every request (`routes.py:715`, `quality_orchestrator.py:1490, 1695`), so every call starts again from the environment value. If TestGen rotates refresh tokens with single use, the second call fails.

**Fix:** keep one client instance per process, or persist the rotated token somewhere writable (the container is read-only, so a database row).

<a id="bug-11"></a>
#### BUG-11 — Smaller correctness issues

**Severity:** Low · **Evidence:** by reading

- `submit_for_review` records `validation_errors` and `last_validation_at` and then raises before committing (`publication.py:46-49`), so a failed validation is never recorded.
- `approve` computes `max(version_number)+1` then inserts (`publication.py:74`); two concurrent approvals produce a unique-constraint 500.
- `complete_periodic_review` reports "follow-up work was created" even when the tasks already existed (`routes.py:497-500`).
- `_jwks_client` calls `.json()` on the discovery response without checking the status (`auth.py:99-103`).
- `@app.on_event("startup")` is deprecated in this FastAPI version; use the lifespan handler.

## 5. Quality orchestrator and TestGen integration

`services/quality_orchestrator.py` is the largest and most ambitious file in the project: 1,845 lines that turn TestGen's profiling and test output into steward-facing findings, evidence and decisions. The plain-language mapping and evidence-sufficiency ideas are good product thinking. The implementation has two paths, mock and real, that share function names but not behaviour, and several parts of the real path were never exercised.

<a id="orch-01"></a>
#### ORCH-01 — Recording a decision on a profiling finding crashes every time

**Severity:** Critical · **Evidence:** verified by running

`decide_hygiene_finding` constructs `QualityDecision(issue_id=..., actor_id=actor_id, ...)` (`quality_orchestrator.py:1154-1165`), but the model's column is `decided_by` (`models.py:303-310`). Reproduced: `TypeError: 'actor_id' is an invalid keyword argument for QualityDecision`. The route catches only `ValueError`, so every per-finding decision from the hygiene workbench returns 500. `decide_issue` at line 1836 uses the correct name; the two were written at different times. Together with [BUG-01](#bug-01), neither decision endpoint works.

**Fix:** rename the keyword. One call in a test would have caught it.

<a id="orch-02"></a>
#### ORCH-02 — Readable finding names lose to numeric codes; one committed test already fails on it

**Severity:** High · **Evidence:** verified by running

`_first_recursive_value` (`:410-426`) returns values in the order they appear in the payload, not in the priority order of the keys it was given, so the comment "always prefer the readable value" at `:447-448` is not what the code does. `tests/test_stage353a_testgen_payload.py::test_testgen_issue_name_preferred_over_numeric_code` fails: `_hygiene_kind({"issue_type": "1002", "issue_type_name": "Non-Standard Blank Values"})` returns `'1002'`. Downstream, the plain-language table at `:605` never matches real payloads, stewards see titles like "Review mail_zip: 1002", and the finding fingerprint is keyed on the code. `_display_column`, `_hygiene_count` and the profile-context lookup have the same ordering dependence.

**Fix:** iterate the keys in priority order and search for each in turn.

<a id="orch-03"></a>
#### ORCH-03 — The expectation workflow exists only in mock mode, and the mock cannot do the hygiene workbench

**Severity:** High · **Evidence:** by reading

In real mode `assess_resource` never proposes expectations (`suggestions = []`, `:1509`), `run_tests` never writes a `QualityResult` (only the mock does, `:1760-1775`) so `latest_result` in the quality API is always null, approved rules are never sent to TestGen as test definitions, failures are never linked to a rule, and the dimension scores (completeness, validity and so on) are synthesised only by the mock (`:1581-1585`). The README's assess → suggest → approve → run → issue loop therefore describes the mock. Conversely, the mock path has none of the real path's deduplication: every mock assessment creates a new hygiene issue and task, every mock run creates new failure issues and never resolves old ones (`:1601-1621, 1777-1799`), and the mock hygiene issue carries no findings list, so the workbench shows "Review 7 profiling findings" with zero findings and nothing to decide. `MockTestGenClient` does not implement the real client's interface, so the real code path cannot be exercised by tests at all.

**Fix:** have the mock client return TestGen-shaped payloads through the same interface as the real one, delete the mode branches inside the orchestrator, and decide explicitly which of the expectation features real mode should support (the README's Stage 4 list already names the missing pieces).

<a id="orch-04"></a>
#### ORCH-04 — Steward decisions can be lost between profiling runs

**Severity:** Medium · **Evidence:** by reading

- The finding fingerprint folds in any `id`, `issue_id` or `definition_id` found in the item (`:736-741`). If TestGen's hygiene rows carry a per-run identifier, no fingerprint matches after a re-profile and every recorded review status, decision and note is dropped (`:1031`), the opposite of the stated intent. This was not confirmed against a live TestGen; profiling the same table group twice and comparing `details.steward_findings[*].fingerprint` will settle it. The one test of decision carry-over uses a fixture with no `id`, so it cannot see this.
- Re-profiling forces the canonical issue back to OPEN and reopens its task regardless of whether any finding is still pending (`:1263-1280`), producing an inbox item titled "Review 0 of N profiling findings".
- Resolving a hygiene issue through the generic decision endpoint leaves every finding PENDING, so the next profile creates a fresh issue with no prior findings (`:1832-1845`).
- `_upsert_hygiene_issue` treats the *oldest* open issue as canonical; `reconcile_asset_quality_issues` keeps the *newest* (`:1212, :1450`).

<a id="orch-05"></a>
#### ORCH-05 — Viewing the quality page resets the connection status in real mode

**Severity:** Medium · **Evidence:** by reading

`ensure_link` unconditionally sets `sync_status` to CONFIGURED (`:81`), and `GET /assets/{id}/quality` calls it for every structured resource and commits (`routes.py:622-631`). So SYNCED, CONNECTED and ERROR are all overwritten on the next page load, and the status the UI shows is meaningless. Any role, including VIEWER, triggers the write.

<a id="orch-06"></a>
#### ORCH-06 — Scores and severities are computed from heuristics that misfire on plausible input

**Severity:** Medium · **Evidence:** by reading

- Only results with `evaluated_count > 0` and a non-null `failed_count` contribute row evidence (`:373-397`); if TestGen reports counts only on failing tests, the score is computed over failures alone and badly understates quality.
- `_normalize_percent` multiplies any value in [0, 1] by 100 (`:141-147`), so a genuine 1 percent becomes 100.
- The overall score is the first `score` found anywhere in the result tree (`:1512-1517`), including nested column-level scores.
- When TestGen returns no score, a new profile row is written carrying the *previous* run's score under the *new* run ID (`:1522-1532`), which fabricates history.
- Warnings are treated as failures and every failure issue is HIGH severity (`:163-168, :1367, :1387`), so a warning becomes a high-priority inbox task; TestGen's own likelihood and impact are captured but never used (`:865-866`).

<a id="orch-07"></a>
#### ORCH-07 — Escalating to expert review puts the task back in "now"

**Severity:** Medium · **Evidence:** by reading

`_reopen_issue_task` always sets the task to OPEN (`:232, :1176, :1844`), including when the issue moves to NEEDS_EXPERT_REVIEW. The task API has a NEEDS_EXPERT_REVIEW status that the inbox maps to the waiting bucket, but neither decision path uses it, so an escalated item stays at the top of the steward's list.

<a id="orch-08"></a>
#### ORCH-08 — No concurrency control, job persistence, retry or pagination

**Severity:** Medium · **Evidence:** by reading

- Every upsert is select-then-insert with no unique constraint on "one open canonical issue per asset, resource and type" (`:86-107, :1204-1222, :1326-1338`); two concurrent assessments create duplicate issues and tasks, and `_reopen_issue_task` then picks one arbitrarily.
- The TestGen run ID is stored only on success (`:1650, :1822`); a restart mid-poll orphans the job. There is no RUNNING state, no way to see a run in progress, and no cancel.
- Only `TestGenError` is caught (`:1644-1647, :1816-1819`); a `KeyError` on an unexpected payload surfaces as a 500 and leaves the link status untouched. The client is single-shot with no retry, so one network blip flips the link to ERROR.
- The columns, hygiene-issues, potential-PII and results endpoints are read once; anything beyond the first page is silently dropped (`_items`, `:110-119`), and an unrecognised payload shape presents as "0 findings, score 100" rather than an error.

<a id="orch-09"></a>
#### ORCH-09 — Captured but unused

**Severity:** Low · **Evidence:** by reading

Potential-PII results are fetched and stored but never become a finding or feed the classification workflow. The `connection_id` and source-mapping fields are stored but never sent to TestGen. Environment defaults are copied into link rows at creation (`:26-34`), so later environment changes do not propagate. A mapping cannot be cleared (empty strings are ignored, `:63`) and the `provider` field is ignored (`:54`). `result = client.wait_for_test_run(run_id)` at `:1703` is never used.

<a id="orch-10"></a>
#### ORCH-10 — Structure

**Severity:** Low · **Evidence:** by reading

`assess_resource` and `run_tests` are 190 and 170 lines with a mode branch in the middle. The service raises `HTTPException` in seven places and `ValueError` in two, so it cannot be tested without FastAPI. The 120-line plain-language table is a literal rebuilt on every call, matches by substring on generic tokens so row order decides outcomes, and hard-codes US ZIP formats. Three recursive walkers with slightly different semantics coexist. `enrich_hygiene_issue` re-parses every issue, including resolved ones, on every GET. Comments refer to stage numbers rather than to what the code does.

**Fix:** move the mapping table to data, raise domain exceptions and translate them in the routes, and split the file as suggested in [CQ-01](#cq-01).

## 6. Frontend

The frontend is a single 1,970-line file with 22 components and 93 pieces of state. It builds cleanly (360 KB of JavaScript, 101 KB gzipped) and contains no cross-site scripting vectors: there is no raw HTML injection, no data-driven links, and no redirects. The problems are about honesty of feedback and structure.

<a id="fe-01"></a>
#### FE-01 — Wizards show "Complete" after a failed save

**Severity:** High · **Evidence:** by reading

The shared `doAction` helper (`frontend/src/main.jsx:61-64`) catches every error and returns nothing, so callers cannot tell success from failure and proceed regardless: the understanding guide advances to its completion step (`:1174-1181`), the governance guide writes the rejected values into local state and dismisses the task (`:1307-1316`), and the official-source and expert-review flows close (`:813-828, :1318-1327`). The only signal is a text banner at the top of the page, off-screen from the button that was clicked, and that banner has no styling (see [FE-08](#fe-08)).

**Fix:** return a boolean (or rethrow) from `doAction` and branch on it; show the outcome next to the control that triggered it.

<a id="fe-02"></a>
#### FE-02 — Silent failures for approvers and viewers

**Severity:** Medium · **Evidence:** by reading

Creating an asset or resource (`:468-507`) and submitting a periodic review (`:1025-1038`) are bare async click handlers with no error handling; several fetches (`:595, :604, :1942`) have no `catch`. The backend correctly rejects APPROVER and VIEWER with 403 for these, so for those roles the button simply does nothing. Only the publication panel and review queue are role-aware; every other wizard is offered to every role.

**Fix:** derive "can edit" from the role once and hide or disable steward-only controls; wrap handlers.

<a id="fe-03"></a>
#### FE-03 — Starting a task from Home or Next Steps opens the wrong guide

**Severity:** High · **Evidence:** by reading

The task-to-tab routing exists three times (`:135-151`, `:154-170`, `:693-714`) and only the third is right. From Steward Home or My Next Steps, a METADATA or CATALOG task ("describe this information", "record where it lives") opens the Governance guide with a mode it does not handle (`:1331, :1358, :1388`), and the guided task never starts.

**Fix:** one `routeForTask()` function used by all three call sites.

<a id="fe-04"></a>
#### FE-04 — No in-flight state on any action, so Publish and Approve can be double-submitted

**Severity:** High · **Evidence:** by reading

Submit, Approve, Publish (`:1693-1751`), "Check this information" and "Run approved checks" (`:1527-1528`), rule approval and every decision button stay enabled while the request is pending. Publish creates an immutable release and calls the catalog; two clicks are two publications. Only the login, password and user-administration screens track a busy flag.

<a id="fe-05"></a>
#### FE-05 — No error boundary; inconsistent null guards produce a blank page

**Severity:** Medium · **Evidence:** by reading

`t.priority.toLowerCase()` (`:354`), `asset.resources.filter` (`:1445`) and `asset.readiness.checks.filter` (`:1607`) throw on missing data while neighbouring code guards the same fields. There is no error boundary and `createRoot` has no fallback, so a render exception is a white screen.

<a id="fe-06"></a>
#### FE-06 — Session expiry is not handled

**Severity:** Medium · **Evidence:** by reading

`api.js:22` clears the token on any 401, but the app only reacts inside the initial `refresh()`; a 401 during any later action leaves the user in the signed-in shell with stale data and every subsequent action failing until a manual reload. Tokens last eight hours with no refresh, so this is a daily event.

**Fix:** broadcast 401 from the API client to the auth state and show a "your session ended, sign in again" screen.

<a id="fe-07"></a>
#### FE-07 — OIDC mode cannot be used

**Severity:** High · **Evidence:** by reading

The backend supports `AUTH_MODE=oidc`, but the frontend always renders the local login form (`:91-93`), whose POST to `/auth/login` returns 400 in that mode. There is no redirect to the identity provider and no token handling, so an SSO deployment (the obvious choice for a state agency, and the only route to MFA today) does not work.

<a id="fe-08"></a>
#### FE-08 — The JSX and the stylesheet have drifted apart

**Severity:** Medium · **Evidence:** by reading

Dozens of class names used in the markup are not defined in `styles.css`: `eyebrow` (about forty uses), `message` (the global feedback banner; the CSS defines `.msg`), `education`, `button-row`, `two-col`, `title-row`, `asset-hero`, `stepper`, `callout`, `timeline`, and every `status-<publication status>` class, so publication badges are never coloured. The stylesheet in turn defines `.hero .cols .title .msg .engine-banner .overview-grid` and others that nothing uses, and `.rule` twice. One side was refactored without the other; a good part of the UI is rendering with browser defaults.

<a id="fe-09"></a>
#### FE-09 — Effects that race, re-run, and wipe unsaved edits

**Severity:** Medium · **Evidence:** by reading

`refresh()` is fired both by `handleLogin` and by the effect that watches sign-in (`:42-72`), doubling every request and letting a slow earlier response overwrite a later one. The quality panel effect (`:1462-1474`) re-runs on every refetch and overwrites the technical-setup form, so editing the TestGen mapping and clicking "Test connection" before "Save" discards the edits; a sibling effect (`:1478-1498`) resets the selected finding and scrolls the page after unrelated actions. Several effects omit dependencies (`:49-58, :940-945, :1290-1295`); an ESLint `react-hooks` rule would have flagged each of these.

<a id="fe-10"></a>
#### FE-10 — Navigation dead ends and orphaned records

**Severity:** Medium · **Evidence:** by reading

The selected asset ID is never validated or cleared on logout (`:47, :74-81`); the next user on the same browser sees "No information has been identified yet" with the asset selector removed (`:596-597`). The Discover wizard creates the asset at step 4 and the location at step 5 with no back or cancel, so a failure or an abandoned wizard leaves an asset with no location, and retrying can create a duplicate system (`:454-507, :588`). Discover always creates a new asset; there is no way to add a location to an existing one.

<a id="fe-11"></a>
#### FE-11 — Accessibility and interaction gaps that matter for a government deployment

**Severity:** Medium · **Evidence:** by reading

- Feedback banner has no `role="status"` or `aria-live`, so screen readers never hear outcomes.
- Choice grids (all wizard options, review answers, term chips) are plain buttons with a `.selected` class and no `aria-pressed`; tabs have no tab roles or arrow-key navigation; the sidebar has no `aria-current`.
- Asset selectors (`:597, :1942`) and several textareas have no label; several labels are not associated with their control.
- No focus management on step or page changes; scrolling is driven by timers.
- Disabled buttons at 45 percent opacity are unreadable and give no reason.
- Publish, "Return for changes", "Deactivate user" and "Reject expectation" have no confirmation; only password reset does.
- `index.html` has no `lang` attribute; Steward Home renders two `h1` elements when the intro is shown.

Section 508 and WCAG 2.1 AA conformance is a normal procurement requirement for state agencies; the current UI would not pass an audit.

<a id="fe-12"></a>
#### FE-12 — Smaller issues

**Severity:** Low · **Evidence:** by reading

- No URL routing: pages and tabs are string state, so browser back exits the app, refresh loses context, and nothing is linkable. Tab titles double as identifiers in six places.
- Steward Home shows "You are caught up" and "0%" before data loads; the review queue shows "—%" and the dashboard "null%" when a score is missing.
- The wizard state machine is reimplemented six times; the async load/error pattern is reimplemented in four styles.
- Classification recommendation, keyword suggestion and review semantics are policy logic living in the UI with no tests.
- Publication history shows raw ISO timestamps; everywhere else uses locale dates.
- The periodic-review interval is hard-coded to 365 days in the client (`:1031`) although the API accepts a value.

## 7. Deployment and operations

The production compose file is the strongest part of the repository. The findings here are the gaps around it.

<a id="ops-01"></a>
#### OPS-01 — There are no database migrations

**Severity:** High · **Evidence:** by reading

The schema is created with `Base.metadata.create_all` at startup (`main.py:48`) and nothing else. `create_all` only creates tables that do not exist; it never adds a column, changes a type or adds a constraint. The first model change after a pilot database exists will either be silently ignored or crash on a missing column, and the rollback procedure in the deployment guide (section 12) has nothing to roll to. The `seed.py` "misplaced engine" block is already a hand-written data migration living inside the demo seed, which shows the need.

**Fix:** add Alembic now, generate the initial revision from the current models, run `alembic upgrade head` as the container entrypoint before uvicorn, and remove `create_all` from startup.

<a id="ops-02"></a>
#### OPS-02 — The nightly backup unit cannot run as shipped

**Severity:** High · **Evidence:** by reading

`deploy/systemd/ai-data-steward-backup.service:7-9` hard-codes `User=eric-graham` and `/home/eric-graham/projects/STEWARD` as the working directory and script path, so it fails on any other host or checkout name. It has no `EnvironmentFile=`, so `BACKUP_RETENTION_DAYS` and `BACKUP_DIR` cannot be set (the backup script reads them from the process environment, not from `.env.production`, although the example file advertises the setting). It has no `OnFailure=`, so a failed backup is visible only in `journalctl`. None of the four guides mention installing it, yet the go-live checklist has "daily backup schedule is enabled".

**Fix:** template the unit from the install script, add `EnvironmentFile=` and an `OnFailure=` notifier, document `systemctl enable --now`, and have `go_live_check.sh` assert the timer is active and the newest backup is under a day old.

<a id="ops-03"></a>
#### OPS-03 — Restore has no safety net, and the password-rotation guidance causes an outage

**Severity:** High · **Evidence:** by reading

`scripts/restore_postgres.sh` stops the application services, drops the database and restores with `--exit-on-error` (lines 30-55). It takes no backup first and sets no `trap`, so a restore that fails midway leaves no database and no running services, with recovery left to the operator. Separately, `scripts/secret_rotation_check.sh:43-45` tells the operator to "restart backend after updating" the PostgreSQL password; `docker compose restart` reuses the container's original environment and does not re-read the env file, so the backend comes back with the old password and crash-loops. The correct step is `up -d backend` to recreate it.

**Fix:** back up before dropping, restore into a scratch database and swap, restart services on failure, and correct the rotation note.

<a id="ops-04"></a>
#### OPS-04 — Backups are not verified, not aged, and not sufficient to rebuild a host

**Severity:** Medium · **Evidence:** by reading

"Verify" runs `pg_restore --list` (`backup_postgres.sh:47-48`, `verify_backup.sh:23-24`), which reads the archive's table of contents and proves nothing about the data blocks or restorability; a three-week-old backup passes and `go_live_check.sh` reports "latest backup verified". `.env.production` (which holds the credentials the restore depends on and the token signing key) and the Caddy data volume (TLS certificates and the ACME account, which is rate-limited on re-issue) are never backed up, so a restore onto a new host is not possible from the backup alone. Backups sit in `backups/` on the same disk as the database volume; off-host copying is a checklist item with no tooling. Retention pruning hides errors with `2>/dev/null || true` and is off by one day (`backup_postgres.sh:50-51`); `verify_backup.sh` hard-codes `backups/` while the backup script honours `BACKUP_DIR`.

**Fix:** restore into a scratch database as the verification step, check backup age, include `.env.production` and the Caddy volume in the bundle (encrypted), and script the off-host copy.

<a id="ops-05"></a>
#### OPS-05 — The health and go-live checks prove less than they report

**Severity:** Medium · **Evidence:** by reading

- `/health` never touches the database (`main.py:61-69`), so a backend with a dead connection pool is healthy to Compose, `ops_status.sh` and the go-live check.
- Once `APP_SITE_ADDRESS` is a hostname, the edge health check's request with `Host: 127.0.0.1` matches no site block and Caddy answers an empty 200, so the edge check passes without traversing the stack.
- `check_production_hardening.py` does not replicate the application's own validator (`config.py:70-118`), so a configuration it passes can still crash-loop at startup; it does not check that `TRUSTED_HOSTS` includes the loopback names the health checks need ([BUG-03](#bug-03)), that hosts and CORS agree with `PUBLIC_APP_URL`, or that `ACME_EMAIL` is set for a public site. Its env-file parser does not strip quotes, so length checks can disagree with what the container sees.
- `go_live_check.sh` checks that `/api/auth/config` returns 200 but never reads the mode; nothing exercises the HTTP to HTTPS redirect, certificate validity, HSTS, or that `/docs` is absent, although all are checklist items.
- `ops_status.sh:50-53` ends its pipeline with `tail`, which exits 0 whether or not `grep` matched, so the "no recent error signatures" fallback never prints and the section is silently empty.

<a id="ops-06"></a>
#### OPS-06 — Frontend image is not reproducible

**Severity:** Medium · **Evidence:** by reading

`frontend/Dockerfile:3-4` copies only `package.json` and runs `npm install`, so the tracked `package-lock.json` is ignored and every build resolves the caret ranges afresh. Neither image has a `.dockerignore`, so `COPY . .` ships a local `node_modules` (macOS binaries into Alpine) and `.git` if present. Built images have no `image:` name, so everything is `latest` and there is no rollback by tag; the deployment guide's rollback section depends on rebuilding from git.

**Fix:** `COPY package.json package-lock.json ./` and `RUN npm ci --no-audit --no-fund`; add `.dockerignore` files; tag images with the git commit.

<a id="ops-07"></a>
#### OPS-07 — Edge and proxy configuration gaps

**Severity:** Medium · **Evidence:** by reading

- The Caddyfile never uses `ACME_EMAIL` (no `email` directive), so the certificate account has no contact for expiry or revocation notices; there is no `log` directive and so no access log; no HSTS ([SEC-06](#sec-06)).
- `nginx.conf` has no `proxy_read_timeout` (default 60 s against a backend that polls TestGen for up to 600 s, [BUG-09](#bug-09)), no gzip, no `Cache-Control` (hashed assets should be `immutable` and `index.html` `no-cache`, otherwise browsers can be stuck on a stale bundle after a deploy), and it forwards a client-supplied `X-Forwarded-Proto`.
- The frontend health check proxies to the backend, so it tests the backend, not the static bundle.

<a id="ops-08"></a>
#### OPS-08 — No continuous integration of any kind

**Severity:** Medium · **Evidence:** by reading

There is no workflow, Makefile, pre-commit configuration, lint, format, type check, dependency audit or image scan in the repository. The test suite has been failing since Version 4.2 and the frontend build was never checked against its lockfile; both would have been caught by a ten-line GitHub Actions file.

**Fix:** a workflow that runs `ruff`, `pytest` (SQLite and a PostgreSQL service), `pip-audit`, `npm ci`, `npm run build`, `npm audit`, and builds both images.

<a id="ops-09"></a>
#### OPS-09 — Hardening and script hygiene details

**Severity:** Low · **Evidence:** by reading

- Images are pinned to tags, not digests; `postgres:16` floats across minor versions; `caddy:2.8` is an old minor; the nginx image runs as root and the frontend service has no `read_only` or `user:`, unlike its siblings.
- Secrets are passed through `environment:` and are visible with `docker inspect`; the postgres image supports `POSTGRES_PASSWORD_FILE` and Compose secrets.
- No CPU, memory or PID limits on any service; `db_net` is not `internal: true`, so the database has outbound internet.
- Scripts write to fixed, predictable paths in `/tmp` rather than `mktemp`; several depend on the current directory rather than the project directory; `stat -c` is GNU-only and produces a false warning on macOS; `verify_network_hardening.sh` ignores the `ENV_FILE` convention its siblings use.
- `.gitignore` lacks `*.db` and `.pytest_cache/`, so the SQLite files the tests create are easy to commit by accident.
- Git internals (`refs/heads/main`, `refs/tags/v2.0-stage1` and so on) are tracked in the working tree under `refs/`; they should be deleted.

## 8. Code quality and structure

The code is readable where it was written carefully and unreadable where it was pasted in a hurry, often in the same file. The structural changes below are what would let a second developer contribute safely.

<a id="cq-01"></a>
#### CQ-01 — Two files carry most of the system

**Severity:** Medium · **Evidence:** by reading

`routes.py` is 850 lines covering assets, tasks, reviews, quality, publication and history; `quality_orchestrator.py` is 1,845 lines; `main.jsx` is 1,970 lines, with a single line of 7,951 characters. About a dozen handlers are written as semicolon-joined one-liners (`routes.py:205, 212, 218-219, 224, 247, 353, 583, 615, 656, 669, 765, 824-839`) next to conventionally formatted ones, which suggests no formatter has ever run.

**Suggested split, backend:** `api/assets.py`, `api/tasks.py`, `api/reviews.py`, `api/quality.py`, `api/publication.py`, each a router; the orchestrator into `quality/mock_engine.py`, `quality/testgen_engine.py`, `quality/issues.py`, `quality/hygiene.py`, `quality/evidence.py`. Run `ruff format` and `ruff check` and add them to CI.

**Suggested split, frontend:** `api/` (one function per endpoint), `state/AuthContext` and `state/DataContext` (removes the `userEmail` and `doAction` props threaded through every component), `pages/`, `features/information/` and `features/quality/`, `components/` for Metric, Status, Choice, WizardShell, and `lib/` for labels, task routing and role rules. Add Prettier and ESLint with the `react-hooks` plugin.

<a id="cq-02"></a>
#### CQ-02 — The API has no declared contract

**Severity:** Medium · **Evidence:** by reading

No route sets a `response_model`; many return ORM objects directly (`return system`, `return rule`, `return profile`), which serialises every column including internal user IDs, and the rest return hand-built dictionaries. The frontend compensates with more than thirty optional-chaining guesses (`asset.readiness?.checks`, `quality?.profiles?.[0]`, `f.evidence?.testgen?.patterns`), so a renamed field fails silently as `undefined`.

**Fix:** Pydantic response models per endpoint. They also make the OpenAPI document useful and let the frontend generate a typed client.

<a id="cq-03"></a>
#### CQ-03 — Enums exist but strings are used everywhere

**Severity:** Medium · **Evidence:** by reading

`MembershipRole` and `PublicationStatus` are defined in `models.py` and then never used; roles, statuses, task types, priorities, decision types and issue types are compared as bare string literals across the code, and the database stores them in unconstrained `String` columns. Typos are silent.

<a id="cq-04"></a>
#### CQ-04 — Dead and environment-specific code

**Severity:** Low · **Evidence:** by reading

- `GovernanceRequirement` is seeded for the demo organisation but never read; readiness uses the hard-coded `PROFILE_FIELDS` in `profile_validator.py`. The per-organisation configurable requirements feature the table implies does not exist.
- `seed.py:224-225` embeds TestGen table-group and test-suite UUIDs from one specific Florida Data Lab environment, and lines 234-292 are a one-off data migration that runs on every development start.
- `StewardshipTask.assigned_to` and `DataAsset.asset_status` exist but nothing sets them.
- `routes.py:24` imports the private `_source_mapping_from_link`; `task_service.py:1-2` imports `datetime` twice; `publisher.py:68` uses `__import__("json")` inline.
- `get_asset_for_org` (seven eager loads) is called twice per mutation, before and after commit; with `expire_on_commit` the second serialisation lazily reloads everything anyway. The quality endpoint queries the latest result per rule in a loop. No list endpoint paginates.

<a id="cq-05"></a>
#### CQ-05 — DCAT output is not standards-valid

**Severity:** Low · **Evidence:** by reading

`dcat_mapper.py` emits `dcat:contactPoint` as a raw string or dictionary (DCAT requires a `vcard:Kind`), `dcat:theme` and `dct:accrualPeriodicity` as literals rather than URIs, and omits `dct:license`, `dct:accessRights`, `dct:issued`, `dct:modified` and `dcat:landingPage`. For a Florida agency the relevant profile is DCAT-US (the federal `data.json` schema), which additionally requires `accessLevel`, `bureauCode` and `programCode`. If catalog interoperability is a goal, validate the output with a SHACL shape or the DCAT-US validator in a test.

<a id="cq-06"></a>
#### CQ-06 — Documentation drift

**Severity:** Low · **Evidence:** by reading

The README describes Stage 3 and documents a `/api/v1/jobs/{job_id}` call that the client's docstring says is intentionally not used; the version string lives in `config.py`, both compose files and `package.json`; `package.json` is still named `ai-data-steward-stage3`. One `CHANGELOG.md` and a single version source would remove the drift.

## 9. Tests and CI

There are 39 tests in 18 files. On a clean checkout with the pinned dependencies, **7 fail and 32 pass**: six with the timezone error described in [BUG-02](#bug-02), and one, `test_testgen_issue_name_preferred_over_numeric_code`, with a genuine regression in the orchestrator ([ORCH-02](#orch-02)). The six are in `test_stage2.py` and `test_stage3.py`, the only tests that exercise the API end to end; the passing ones are mostly unit tests of private helpers. The timezone failures date from the periodic-review feature (Version 4.2), so the suite has been red for the last four versions without anyone noticing, which is the strongest argument for CI.

- There is no `conftest.py`. Each API test file sets `DATABASE_URL` in `os.environ` at import time, but `settings` is a module-level singleton created by whichever test module imports the app first, so in a full run the later assignments are ignored and the app uses the config default, or whatever `backend/.env` says. The likeliest explanation for the suite ever passing on the author's machine is that a local `.env` pointed it at the development PostgreSQL, where the timezone comparison works. The tests then also write SQLite files into `backend/` and leave them there.
- Several tests do not test behaviour: `test_stage351_catalog_context.py` reads `seed.py` as text and asserts that UUID strings appear in it; `test_stage41`, `42d` and `43a` assert only that a route path or name exists; `test_stage44e2` tests SQLAlchemy's own `URL.create`.
- Tests are named by release stage (`test_stage44e2_database_url.py`) rather than by behaviour, which makes it hard to see what is covered.
- Not covered at all: local login and lockout (the 429 path is never hit), token validation and expiry, role enforcement on any mutating route, tenant isolation (a user in organisation A reading organisation B's asset), the publication state machine (submit, approve, reject, publish, needs-update), every administration route including the last-administrator guard, the production configuration validator the go-live process relies on, the CKAN publisher and DCAT mapper, the real TestGen client and the whole real-mode orchestrator path (no HTTP mocking exists), `decide_hygiene_finding` (a single call would have caught [ORCH-01](#orch-01)), and the frontend (no test runner exists).
- There is no CI configuration of any kind ([OPS-08](#ops-08)).

**Recommendation:** a `conftest.py` with a fresh SQLite (and, in CI, PostgreSQL) database per test and fixtures for each role; a GitHub Actions workflow running `ruff`, `pytest`, `pip-audit`, `npm ci`, `npm run build` and `npm audit`; and Vitest with React Testing Library for the wizard flows. Add one test per finding in this report as it is fixed.

## 10. Missing features and recommendations

Grouped by who would ask for them. Items marked **table exists** already have a database column or table that nothing uses, so they are cheaper than they look.

### Platform, before pilot

- **Schema migrations** (Alembic) and a documented upgrade path ([OPS-01](#ops-01)).
- **Background jobs** for TestGen profiling and test runs with progress in the UI ([BUG-09](#bug-09)), then **scheduled recurring runs** per resource (the README lists this as a Stage 4 candidate).
- **Audit log** and a read-only view of it for administrators ([SEC-07](#sec-07)).
- **Notifications**: e-mail (or Teams webhook) when a task is assigned, a review is requested, a review is due, or a quality run finds new issues. Today nothing leaves the application.
- **SSO front-end flow** for the existing OIDC backend mode, which is also the route to multi-factor authentication ([FE-07](#fe-07)).
- **Pagination, search, filter and sort** on assets, tasks, the review queue and users. Fine for a pilot of thirty assets; blocking beyond that.
- **Structured JSON logging with request IDs**, and a metrics endpoint, so the operator can answer "what happened at 3pm" without reading uvicorn output.

### Stewards

- **Task assignment** **table exists** (`assigned_to`), due dates, reassignment, and comments on a task. Expert review currently changes a status and stops; it should route to a named person.
- **Edit and remove locations**, edit systems, rename or archive assets **table exists** (`asset_status`). Today the only way to add a location is the five-step Discover wizard, which always creates a new asset, and nothing can be deleted.
- **Reviewer comments**: approvers currently send canned text and stewards never see a reason for a return. The events table already stores comments; the UI needs a field and a display.
- **Quality history and trends**: profiles and results are stored per run but resolved issues and past decisions are filtered out of the UI and there are no charts. A simple score-over-time line per asset would be immediately useful.
- **Rule authoring**: the API can create expectations (`POST /assets/{id}/quality/rules`) but the UI cannot, and approved expectations are never pushed back into TestGen as test definitions (a README Stage 4 item).
- **Evidence attachments** on decisions, and a **business glossary** so terms used in definitions are shared across assets.
- **Export**: CSV of the inventory and task list; a DCAT feed endpoint (`/catalog.jsonld` and a DCAT-US `data.json`) so the catalog can be harvested without CKAN.

### Administrators

- **Configurable governance requirements per organisation** **table exists** (`governance_requirements`), and a configurable classification scheme (Florida public-records categories and exemptions rather than free text).
- **Organisation switching** for users with several memberships and a real cross-organisation view for ENTERPRISE_ADMIN.
- **Self-service password reset** and an account page (the UI already tells users to "manage your password from your account", which does not exist).
- **CKAN synchronisation**: update and remove resources, unpublish, and a link from publishing history to the catalog entry.

## 11. What is done well

A review that only lists problems misrepresents the codebase. These are the things the author should keep doing.

- **Password handling.** scrypt with a per-user salt and `hmac.compare_digest`; a forced change on first login; a bootstrap command that prompts rather than taking the password as an argument.
- **Token design.** Issuer, audience and expiry claims; a renamed or deactivated account invalidates its tokens on the next request.
- **Production configuration validator.** Refuses demo auth, wildcard CORS or hosts, seed data, API docs and placeholder secrets in production. This is exactly the kind of guard that prevents the most common self-hosting accidents.
- **Separation of duties.** A submitter cannot approve their own asset; the last administrator cannot be demoted or deactivated; an administrator cannot lock themselves out.
- **Immutable releases.** Every approval snapshots the asset and hashes it; publication history shows the versions. This is the right model for an auditable catalog.
- **Container hardening.** Three isolated networks, read-only root filesystems with tmpfs, `no-new-privileges`, a non-root backend user, health checks with dependency ordering, log rotation, and only the edge publishing ports.
- **Operator tooling.** Backup, verify and restore scripts with an explicit confirmation word; a go-live check; a fresh-install script that generates secrets rather than shipping defaults; guides that are specific rather than generic.
- **Product writing.** The steward-facing copy is plain, non-judgemental and consistent, and the "what you are not expected to do" framing is unusually thoughtful. TestGen terminology never leaks into the UI.
- **Hygiene.** No secrets in git history; the frontend dependency tree is clean; the demo-mode header is correctly ignored outside demo mode.

## 12. Appendix: verification log

Commands were run from a clean checkout of `92c59ef` in an isolated virtual environment on Python 3.13 with the pinned `requirements.txt`. The harness used FastAPI's `TestClient` with the application's real startup (table creation and demo seed). Output is trimmed to the relevant lines.

Test suite

```
$ python -m pytest -q
FAILED tests/test_stage2.py::test_dashboard_and_tasks - TypeError: can't compare offset-naive and offset-aware datetimes
FAILED tests/test_stage2.py::test_quality_is_attached_to_asset - TypeError: ...
FAILED tests/test_stage2.py::test_submitter_cannot_self_approve - TypeError: ...
FAILED tests/test_stage3.py::test_testgen_mock_status - TypeError: ...
FAILED tests/test_stage3.py::test_profile_generates_quality_workflow - TypeError: ...
FAILED tests/test_stage3.py::test_approved_rule_run_creates_issue_and_decision_resolves_it - TypeError: ...
FAILED tests/test_stage353a_testgen_payload.py::test_testgen_issue_name_preferred_over_numeric_code
    AssertionError: assert '1002' == 'Non-Standard Blank Values'
7 failed, 32 passed, 3 warnings in 1.54s
```

Orchestrator (ORCH-01, SEC-10)

```
>>> decide_hygiene_finding(db, issue, actor_id=1, fingerprint, "BAD_DATA", "x")
TypeError: 'actor_id' is an invalid keyword argument for QualityDecision      (models.py column is decided_by)

>>> httpx.Request("POST", f"{base}/api/v1/table-groups/{tg}/profiling-runs").url   # pinned httpx 0.28.1
tg = "x?limit=1#frag"              -> /api/v1/table-groups/x?limit=1            (profiling-runs segment dropped)
tg = "x/../../projects/other/jobs" -> /api/v1/projects/other/jobs/profiling-runs
```

Demo mode, SQLite, seeded (BUG-01, BUG-02, SEC-07, SEC-08, SEC-10)

```
POST /api/quality/issues/999/decision  body={"decision_type":"BAD_DATA","notes":"x"}
  -> 422 {"detail":[{"type":"missing","loc":["query","HygieneFindingDecisionCreate"],"msg":"Field required"}]}

GET /api/assets/1/reviews
  -> TypeError: can't compare offset-naive and offset-aware datetimes  @ app/api/routes.py:373
GET /api/tasks  (also /api/dashboard, POST /api/assets/1/resources, ...)
  -> TypeError: can't compare offset-naive and offset-aware datetimes  @ app/services/task_service.py:39

GET /api/me            X-User-Email: admin@demo.gov   -> 200 role=ORG_ADMIN
GET /api/admin/users   X-User-Email: admin@demo.gov   -> 200 (4 users)

POST /api/systems  {"name": "x" * 300}                -> 200 (stored; PostgreSQL would raise on String(255))
POST /api/assets/1/resources {"structure_type":"banana", ...}  -> accepted by schema

GET /health -> {"status":"ok","version":"0.4.4-h","environment":"test","auth_mode":"demo","publisher":"mock"}
```

TRUSTED_HOSTS=steward.example.com, as in .env.domain.example (BUG-03)

```
GET /health  Host: 127.0.0.1:8000      -> 400 Invalid host header   (this is what the Docker health check sends)
GET /health  Host: steward.example.com -> 200
```

Local mode, AUTH_LOGIN_MAX_FAILURES=3 (SEC-01)

```
POST /api/auth/login x5, same client, wrong password
  -> [401, 401, 401, 429, 429]                     throttle works for a fixed address
POST /api/auth/login x8, X-Forwarded-For: 10.0.0.{0..7}, same account
  -> [401, 401, 401, 401, 401, 401, 401, 401]     never throttled

GET /api/me  X-User-Email: admin@demo.gov  -> 401 "Sign in required"   header correctly ignored in local mode
```

Dependency audit (SEC-02)

```
$ pip-audit -r backend/requirements.txt
pyjwt      2.10.1  PYSEC-2025-183, PYSEC-2026-120, -175, -176, -177, -178, -179   fix: 2.13.0
starlette  0.47.3  PYSEC-2026-161, -248, -249, -1942, -2280, -2281               fix: 1.3.1 (via fastapi)
pytest     8.4.1   PYSEC-2026-1845                                              fix: 9.0.3

$ npm audit --package-lock-only
found 0 vulnerabilities
```

Frontend build and git history

```
$ npm ci && npm run build
dist/assets/index-D9xJXl3t.js   360.86 kB │ gzip: 101.41 kB
✓ built in 693ms

$ git log -p --all | grep -E '(SECRET|PASSWORD|TOKEN|API_KEY)=...'   -> no committed secret values
$ git ls-files refs/                                                  -> refs/heads/main, refs/heads/stage2, refs/tags/v2.0-stage1, ... (git internals tracked)
```

---

_Prepared 14 September 2026 against commit 92c59ef. Findings tagged _verified by running_ were reproduced by execution during the review; all others are from reading the code at the cited lines. No files in the repository were changed._
