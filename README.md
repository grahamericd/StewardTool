# AI Data Steward — Stage 2

Stage 2 turns the Stage 1 catalog/publication POC into a broader governance platform foundation.

## What Stage 2 adds

- Configurable **OIDC authentication** path (with demo mode retained for local demos)
- Configurable **real CKAN publisher** plus mock publisher
- DCAT JSON-LD generated only at the publication boundary
- DQV-style quality summary in the DCAT output
- Plain-language **catalog profile/readiness validator**
- Metadata tagging workflow: business area, search terms, update frequency, contact
- Governance fields: owner, steward, classification, retention
- Automatically generated **Stewardship Inbox** tasks from governance gaps
- Data-quality profiles, rules, results, and quality-failure tasks
- Data Asset 360 tabs for Metadata, Governance, Quality, and Publication
- Immutable release snapshots and publication audit history retained from Stage 1
- API tests and a stronger configuration surface

## The design principle

> The user never needs to know they are creating DCAT metadata.

The UI asks normal business questions. The backend maps approved, governed records to DCAT only when an immutable release is published.

## Run locally

### Option A — Docker for PostgreSQL + backend

```bash
cd ai-data-steward-stage2
docker compose up --build
```

Then in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### Option B — Backend with SQLite

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend defaults to SQLite if `DATABASE_URL` is not set.

## Demo identities

- Steward: `steward@demo.gov`
- Approver: `approver@demo.gov`
- Org Admin: `admin@demo.gov`
- Enterprise Admin: `enterprise@demo.gov`

The UI includes a demo role switcher. In real deployments switch `AUTH_MODE=oidc`.

## OIDC configuration

Copy `backend/.env.example` to `.env` and configure:

```text
AUTH_MODE=oidc
OIDC_ISSUER=https://your-identity-provider/
OIDC_AUDIENCE=your-api-audience
OIDC_JWKS_URL=
OIDC_EMAIL_CLAIM=email
```

Users still need a provisioned `app_users` record and organization membership. Stage 2 validates the bearer JWT and maps the configured email claim to that user.

## Real CKAN publishing

By default publication uses the mock CKAN adapter. To publish to an actual CKAN instance:

```text
CATALOG_PUBLISHER=ckan
CKAN_BASE_URL=https://catalog.example.gov
CKAN_API_KEY=...
CKAN_OWNER_ORG=organization-slug
```

The real adapter uses CKAN's Action API to create/update packages and create resources. It also stores the generated DCAT JSON-LD as CKAN metadata so a later CKAN/DCAT profile can consume or expose it without changing the stewardship UX.

**Important:** resource updates are deliberately simple in Stage 2. Before production, reconcile CKAN resources by stable external IDs instead of blindly creating a new resource on every republish.

## Quality integration model

Stage 2 creates a clean integration boundary for the quality engine:

```text
catalog.data_resource
        ↓
quality_profiles
quality_rules
quality_results
        ↓
stewardship_tasks
```

The seeded `Application` asset includes a quality profile and a failed approved rule so the UI demonstrates quality as part of governance rather than a separate application.

Your existing AI Data Steward data-quality engine can integrate by writing equivalent profile/rule/result records or by adding an adapter that translates its current `metadata.dataset_registry`, `dq.rule`, and `dq.results` tables into these endpoints.

## Current publication profile

The Stage 2 validator checks, in plain language:

- Business definition
- Business owner
- Data steward
- At least one resource
- Business area
- Search terms
- Update frequency
- Contact point
- Authoritative source
- Classification
- Retention
- Quality assessment

Only the required subset blocks submission. The rest contributes to Governance Readiness and creates stewardship tasks.

## Run tests

```bash
cd backend
pytest -q
```

## Recommended next work

Stage 3 should focus on integration and governance intelligence rather than more shell work:

- Map the existing PostgreSQL quality engine to `data_resource`
- Add real metadata extraction for CSV/database resources
- Add AI-proposed business definitions and tags with human approval
- Add configurable organization-specific governance requirements
- Add stable CKAN resource synchronization
- Add DCAT-US / Florida application-profile mapping and SHACL-style validation
- Add data-element/column cataloging and classification
- Add reference-data and lineage relationships
