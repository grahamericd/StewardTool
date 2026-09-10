# AI Data Steward — Stage 1

Production-shaped proof of concept for:

**User → Organization → System → Data Asset → Resource → Metadata → Governance Readiness → Review → Approval → Publication → CKAN adapter**

The steward never needs to know they are creating DCAT metadata. The application asks plain-language questions and maps approved releases to DCAT-style metadata only at publication time.

## Included

- Multi-organization model
- Users and organization memberships
- Demo role switching
- Systems, data assets, resources and metadata
- Structured / semi-structured / unstructured resources
- Governance-readiness score
- Publication lifecycle: DRAFT → IN_REVIEW → APPROVED → PUBLISHED, plus NEEDS_UPDATE / REJECTED / ARCHIVED
- Immutable release snapshots and audit events
- DCAT JSON-LD mapper
- Mock CKAN publisher
- React/Vite demo UI
- PostgreSQL via Docker Compose
- Seeded Business Licensing scenario
- Quality-engine integration hook

## Run

From this folder:

```bash
docker compose up --build
```

API: http://localhost:8000  
Swagger: http://localhost:8000/docs

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Demo users

- Steward — steward@demo.gov
- Approver — approver@demo.gov
- Org Admin — admin@demo.gov
- Enterprise Admin — enterprise@demo.gov

Stage 1 uses `X-User-Email` as a demo identity header. Replace it with SSO/OIDC in Stage 2.

## Demo flow

1. Open **Discover Data** as Steward.
2. Start with Business Licensing System.
3. Identify Application as a data asset.
4. Add Submitted License Applications as a PDF collection.
5. Review Data Asset 360 and Governance Readiness.
6. Submit for review.
7. Switch to Approver and approve.
8. Publish.
9. Inspect Publication History to see the immutable snapshot and generated DCAT JSON-LD.

## Existing quality engine integration

Your current quality implementation remains separate for now. Stage 2 should link `catalog.data_resource` to the existing dataset registry so profiles, rules, results and remediation appear under the same Data Asset 360 experience.
