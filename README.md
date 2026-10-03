# AI Data Steward

AI Data Steward is a guided, human-in-the-loop data-governance platform for
people who understand their organization's information but may not know formal
governance terminology. It helps stewards identify information assets, explain
what they mean, record where they live, make governance decisions, interpret
quality evidence, complete stewardship work, and publish approved information.

The product is intentionally not a generic metadata spreadsheet, centralized
data-ingestion platform, TestGen replacement, or unattended AI decision-maker.
Technical standards such as DCAT and DQV are produced from business-friendly
answers rather than required from ordinary users.

## Current workflow

```text
Organization
    -> Systems and familiar tools
    -> Information assets
    -> Resources and locations
    -> Business meaning and structured metadata
    -> Ownership, classification, retention, and official source
    -> Quality evidence and human decisions
    -> Stewardship tasks and periodic review
    -> Submit -> review -> approve
    -> Immutable release snapshot
    -> DCAT mapping -> CKAN or enterprise catalog
```

The main frontend areas are:

- **Steward Home**: current priorities, stewardship progress, and guided work.
- **My Information**: the organization's known systems, assets, resources,
    readiness, quality, tasks, and publication status.
- **Discover Information**: a guided System -> Information -> Resource flow.
- **Information Details**: Asset 360 for understanding, locations, governance,
    quality, review, and publication.
- **My Next Steps**: actionable tasks explaining what is missing, why it
    matters, and what completion means.
- **Review Queue** and **Publishing History**: approval and release workflows
    for reviewers and administrators.
- **User Administration**: organization user and role management for admins.

## Roles and authorization

The backend enforces organization and role boundaries. Frontend navigation is
only a convenience and is not the security boundary.

| Role | Typical responsibility |
| --- | --- |
| `STEWARD` | Discover information, maintain business metadata, review quality, and complete stewardship tasks. |
| `APPROVER` | Review submissions and approve or reject releases. |
| `ORG_ADMIN` | Manage organization users and roles, and perform steward or reviewer work. |
| `VIEWER` | Read permitted organization information. |
| `ENTERPRISE_ADMIN` | Enterprise-level administrative and governance access. |

Demo mode includes seeded identities such as `steward@demo.gov`,
`approver@demo.gov`, `admin@demo.gov`, and `enterprise@demo.gov`. Demo mode
trusts the `X-User-Email` header and must never be used for public production.

Production authentication supports local credentials with bearer-token sessions
or OIDC. Local authentication includes password hashing, temporary passwords,
forced first-login password changes, expiration, login throttling, and account
provisioning through organization membership.

## Data quality boundary

The integration deliberately separates technical execution from governance:

- **TestGen** performs profiling, technical tests, observations, and quality
    scoring.
- **AI Data Steward** stores the integration mapping, interprets evidence,
    creates stewardship tasks, and records human decisions.
- **DCAT/CKAN** provide standards-based catalog representation and publication.

AI Data Steward does not silently classify a finding as bad data. A steward can
record that data is incorrect, an exception is valid, an expectation should
change, or expert review is required.

## TestGen modes

`TESTGEN_MODE=mock` is the default for development and automated testing. The
deterministic adapter exercises profiling, quality scores, suggested rules,
rule decisions, test runs, quality issues, inbox tasks, and guided issue
resolution without requiring a TestGen installation.

`TESTGEN_MODE=real` uses the configured TestGen REST API. Configure the
connection, authentication, project, table group, and test suite, then map a
resource from Information Details -> Quality. Install TestGen separately so it
remains a replaceable technical engine.

The modes are intentionally not feature-equivalent:

| Capability | `mock` | `real` |
| --- | --- | --- |
| Profiling run and quality score | Supported | Supported |
| Hygiene findings and guided finding workbench | No findings produced | Supported when returned by TestGen |
| Suggested expectations | Supported | Not yet proposed automatically |
| Approved expectations pushed into TestGen | Not applicable | Not yet implemented |
| Per-rule test results | Supported | Not yet fully populated |
| Dimension scores such as completeness and validity | Synthesized | Not yet populated consistently |

Useful TestGen settings are:

```env
TESTGEN_MODE=real
TESTGEN_BASE_URL=http://host.docker.internal:8530
TESTGEN_AUTH_MODE=oauth_refresh
TESTGEN_OAUTH_CLIENT_ID=
TESTGEN_OAUTH_CLIENT_SECRET=
TESTGEN_OAUTH_REFRESH_TOKEN=
TESTGEN_PROJECT_CODE=
TESTGEN_TABLE_GROUP_ID=
TESTGEN_TEST_SUITE_ID=
```

Bearer authentication can be selected with `TESTGEN_AUTH_MODE=bearer` and
`TESTGEN_TOKEN`. Never commit TestGen credentials or tokens.

## Catalog publication

Publication is based on an approved release, not the current mutable working
record:

1. Readiness checks validate the asset.
2. A steward submits it for review.
3. An approver reviews and approves or rejects it.
4. Approval creates an immutable JSON snapshot and SHA-256 hash.
5. The snapshot is mapped to DCAT/DQV JSON-LD.
6. The configured publisher publishes to mock CKAN or real CKAN.

Editing a published asset changes its status to `NEEDS_UPDATE`, preserving the
previous release history. Configure real CKAN publishing with:

```env
CATALOG_PUBLISHER=ckan
CKAN_BASE_URL=https://catalog.example.gov
CKAN_API_KEY=<secret>
CKAN_OWNER_ORG=<optional-owner-organization>
```

Automated tests use the mock publisher and must not make uncontrolled live CKAN
calls.

## Development

The development compose file keeps the development database separate from
production:

- PostgreSQL: `127.0.0.1:5434`
- Backend: `127.0.0.1:8001`
- Frontend dev server: `http://localhost:5173`
- Docker project: `steward-dev`
- Authentication: `AUTH_MODE=demo`
- Database volume: `ads_stage3_pgdata`, separate from the production volume.

When Vite runs directly, the frontend continues to call `/api`. The
development-only proxy in `frontend/vite.config.js` forwards `/api/*` to
`http://127.0.0.1:8001/api/*`, so the same frontend API path works in both DEV
and production. Do not set `VITE_API_BASE` for the normal DEV workflow.

Start the development stack:

```bash
docker compose -p steward-dev -f docker-compose.dev.yml up --build -d
```

Then run the Vite frontend separately:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Development defaults to demo authentication,
seeded data, mock CKAN, and mock TestGen. Do not point development or tests at
seeded data, mock CKAN, and mock TestGen. Verify
`http://localhost:5173/api/auth/config` returns JSON from the DEV backend, not
the Vite application HTML. Do not point development or tests at the production
database volume or expose the DEV backend/database beyond localhost.

Stop the isolated DEV stack with:

```bash
docker compose -p steward-dev -f docker-compose.dev.yml down
```

Run the regression checks:

```bash
cd backend
pytest

cd ../frontend
npm run build
```

The backend test suite covers quality workflows, task guidance, publication,
periodic review, authentication, user administration, hardening, and
backward-compatible metadata behavior.

## Configuration

The main settings are defined in `backend/app/config.py`. Copy the appropriate
example environment file rather than committing secrets.

Common settings include:

| Area | Settings |
| --- | --- |
| Runtime | `APP_ENV`, `PUBLIC_APP_URL`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, `ENABLE_API_DOCS`, `SEED_DEMO_DATA` |
| Database | `DATABASE_URL` or `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` |
| Authentication | `AUTH_MODE`, `AUTH_SECRET_KEY`, password and login-throttling settings, OIDC settings |
| Catalog | `CATALOG_PUBLISHER`, `CKAN_BASE_URL`, `CKAN_API_KEY`, `CKAN_OWNER_ORG` |
| TestGen | `TESTGEN_MODE`, base URL, authentication, project, table group, suite, and timeout settings |
| Publication | `CATALOG_PROFILE_NAME`, `MINIMUM_SUBMISSION_SCORE` |

Production validation rejects demo authentication, wildcard CORS or trusted
hosts, seeded demo data, enabled API docs, placeholder secrets, and incomplete
real CKAN/TestGen configuration.

## Production topology

The production compose stack contains four services:

```text
Browser / optional Cloudflare
                    |
                Caddy
                    |
            nginx frontend
                    |
             FastAPI backend
                    |
            PostgreSQL 16
```

Only the Caddy edge should be reachable from the public network. The backend,
frontend, and database communicate over Docker networks. Caddy provides the
security headers, compressed responses, JSON access logs, and the long proxy
read timeout needed for synchronous TestGen polling. Direct Caddy HTTPS is
supported through `APP_SITE_ADDRESS`; it can also be placed behind a managed
edge such as Cloudflare.

Before a production deployment:

1. Configure `.env.production` with mode `600` permissions.
2. Use local or OIDC authentication, never demo mode.
3. Rotate development or exposed credentials.
4. Create and verify a PostgreSQL backup.
5. Confirm only required public ports are exposed.
6. Run the production hardening and go-live checks.

Start production with:

```bash
docker compose --env-file .env.production \
    -f docker-compose.prod.yml up --build -d
```

Useful operational commands and recovery procedures are documented in
[PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md). The main
checks are:

```bash
./scripts/check_production_hardening.py .env.production
./scripts/go_live_check.sh https://your-domain.example
./scripts/backup_postgres.sh
./scripts/verify_backup.sh
```

Do not delete production volumes, expose PostgreSQL, overwrite production
configuration casually, or copy development files or databases directly into
production. Release through version control, verified tests, manual acceptance,
backup, and controlled deployment.

## Repository map

```text
backend/app/models.py                 Domain model
backend/app/api/                      FastAPI routes and auth/admin APIs
backend/app/services/                 Readiness, tasks, quality, snapshots, publication
backend/app/integrations/testgen/     TestGen adapter
backend/tests/                        Backend regression tests
frontend/src/main.jsx                 Current React application
frontend/src/api.js                   Frontend API/auth helper
frontend/vite.config.js               DEV-only `/api` proxy to FastAPI on port 8001
docker-compose.dev.yml                Isolated development stack
docker-compose.prod.yml               Production-shaped stack
deploy/caddy/Caddyfile                Production edge configuration
scripts/                              Backup, hardening, install, and smoke checks
docs/ci/                              CI proposal, intentionally outside GitHub's active workflow directory
```

## Product direction

Future work should deepen guided metadata capture, discovery, governance
evidence, quality trends, remediation, enterprise catalog interoperability,
and relationships between information across systems. New features should
answer seven questions: what the steward is trying to understand, what
governance concept that represents, how it is stored, how it maps to standards,
what evidence supports it, who approved it, and how it becomes actionable or
publishable.
