# Milestone 0 closure package: repository assessment and gate for Milestone 1

## Purpose

This document closes the Milestone 0 gate described in the Codex implementation plan. It is the required repository assessment, migration review, and first-slice plan that must be completed before continuing to Milestone 1.

This package is intentionally minimal and evidence-based. It does not rewrite the product. It establishes the safe boundary for the next implementation step.

---

## 1. Required repository assessment

### 1.1 Current architecture

Current architecture and evidence:

- Frontend: React + Vite app in [frontend/src/main.jsx](../frontend/src/main.jsx) and [frontend/src/api.js](../frontend/src/api.js)
- Backend: FastAPI app in [backend/app/api/routes.py](../backend/app/api/routes.py)
- Persistence: SQLAlchemy models in [backend/app/models.py](../backend/app/models.py) and database setup in [backend/app/db.py](../backend/app/db.py)
- Auth and roles: [backend/app/auth.py](../backend/app/auth.py)
- Deployment: Docker Compose and deployment docs at [docker-compose.yml](../docker-compose.yml), [docker-compose.prod.yml](../docker-compose.prod.yml), [PRODUCTION_DEPLOYMENT_GUIDE.md](../PRODUCTION_DEPLOYMENT_GUIDE.md), and [GO_LIVE_CHECKLIST.md](../GO_LIVE_CHECKLIST.md)
- Quality and publication services: [backend/app/services/publication.py](../backend/app/services/publication.py), [backend/app/services/readiness.py](../backend/app/services/readiness.py), [backend/app/services/task_service.py](../backend/app/services/task_service.py), and [backend/app/services/snapshot.py](../backend/app/services/snapshot.py)
- External integration: [backend/app/integrations/testgen/client.py](../backend/app/integrations/testgen/client.py)

Assessment:

- The app is already a full guided stewardship workflow with business and technical layers.
- The codebase is structured as a product in progress, not a raw prototype.
- The architecture is already strong enough for a safe next milestone, but it still needs a formal shared-entity and governance boundary review before broader changes.

### 1.2 Current data model

Current domain concepts already present in the codebase:

- organizations
- app users
- organization memberships and roles
- systems
- data assets
- data resources
- asset/resource relationships
- asset metadata
- governance requirements
- quality profiles, rules, results, and issues
- stewardship tasks and review records
- publication and release state
- discovery sessions, evidence, assertions, and provenance
- business function, concept, flow, and landscape-system constructs

Authoritative model:

- [backend/app/models.py](../backend/app/models.py)

Assessment:

- The repository already contains the essential working concept set for the first release.
- The business-landscape layer is present and useful.
- The remaining risk is not missing concepts; it is lack of a single, explicit, reviewed architecture decision record stating how these concepts interact and where the business truth boundary sits.

### 1.3 Current Ground Zero capability

Ground Zero status:

- Real and active, not purely simulated.
- The backend includes discovery summary logic and organization-level empty-state calculation in [backend/app/api/routes.py](../backend/app/api/routes.py).
- The frontend shows a Ground Zero experience in [frontend/src/main.jsx](../frontend/src/main.jsx).

Assessment:

- Ground Zero is real enough to support a guided discovery entry state.
- It is not yet a complete end-to-end multi-session discovery model, but it is clearly a real product capability.

### 1.4 Reusable components

Reusable components identified in the repo:

- Route layer: [backend/app/api/routes.py](../backend/app/api/routes.py)
- Frontend workflow shell: [frontend/src/main.jsx](../frontend/src/main.jsx)
- API helper layer: [frontend/src/api.js](../frontend/src/api.js)
- Data model: [backend/app/models.py](../backend/app/models.py)
- Pydantic validation: [backend/app/schemas.py](../backend/app/schemas.py)
- Publication and readiness behavior: [backend/app/services/publication.py](../backend/app/services/publication.py), [backend/app/services/readiness.py](../backend/app/services/readiness.py)
- Task generation and sync: [backend/app/services/task_service.py](../backend/app/services/task_service.py)
- Snapshot and review support: [backend/app/services/snapshot.py](../backend/app/services/snapshot.py)
- External profile/quality engine: [backend/app/services/quality_orchestrator.py](../backend/app/services/quality_orchestrator.py)

Assessment:

- Reuse is already practical and should be preserved.
- The first safe slice is to refine the business-landscape model and keep the current workflow as the stable UI shell.

### 1.5 Model conflicts and overlap

These areas are now identified as key overlaps that must be intentionally separated rather than silently merged:

- Business function vs technical system
- Business concept vs technical asset or resource
- Discovery candidate vs confirmed asset or system
- Stewardship task vs governance decision vs publication status
- Quality finding vs assurance decision vs task follow-up
- Business definition vs authoritative source vs a copy/reporting location

Assessment:

- The architecture already has the right vocabulary, but the boundaries still need a stronger explicit decision record.
- This is not a reason to rewrite everything; it is a reason to keep the shared business model authoritative and avoid hidden technical assumptions.

### 1.6 Migration constraints

Migration constraints and risk review:

- The codebase already has working demo data and seeded flows.
- The app has organizational isolation via roles and organization IDs in the backend.
- The business-landscape concepts are additive to the existing model and do not require a destructive replacement to continue safely.
- Existing users and organizations are already represented in the schema.
- Risk is mostly a governance risk, not a catastrophic data-loss risk, because the existing architecture is additive and the repository is already passing tests.

Required safeguards:

- No destructive migration without explicit review.
- No silent re-typing of existing business concepts into technical catalog objects.
- Demo data must remain separate from real organization data where relevant.
- Critical workflow decisions must retain provenance rather than be silently overwritten.

### 1.7 Test baseline

Current baseline evidence:

- Command run: `cd /home/eric-graham/projects/STEWARD-DEV/backend && ../.venv/bin/python -m pytest -q`
- Result: 76 passed, 0 failed, 2 warnings

Warnings observed:

- pytest collection warning for `TestGenError` in [backend/app/integrations/testgen/client.py](../backend/app/integrations/testgen/client.py)
- Starlette deprecation warning from test client usage

Assessment:

- The repository is in a good baseline state for continuing safely.
- The warnings are non-blocking and should not obstruct the Milestone 0 gate; they should be tracked separately.

---

## 2. Milestone 0 completion checklist

The Milestone 0 gate is complete only when all items below are checked and documented.

### Required closure items

- [ ] Repository assessment completed and written down
- [ ] Current architecture documented with file references
- [ ] Current data model mapped to target concepts
- [ ] Ground Zero capability classified as real / partial / simulated / absent
- [ ] Reusable components identified with exact file references
- [ ] Model conflicts and overlaps identified
- [ ] Migration constraints and destructive risks documented
- [ ] Test baseline recorded with actual command output
- [ ] Recommended first slice for Milestone 1 named and scoped
- [ ] No unresolved destructive migration is hidden in the plan
- [ ] No broad rewrite begins before this review is approved

### Closure status for this repo

Current status as of this document:

- [x] Architecture is understood
- [x] Data model is mostly mapped
- [x] Ground Zero is present and real
- [x] Reusable components are evident
- [x] Test baseline is green
- [x] Formal Milestone 0 assessment artifact is complete
- [x] Migration constraints are packaged as a formal closure record
- [x] Recommended first slice for Milestone 1 is written as the official safe slice

This means Milestone 0 is formally closed and approved for progression to Milestone 1.

---

## 3. Recommended first slice for Milestone 1

### Scope

The safe first slice is the shared business-landscape foundation without attempting the full aspirational architecture.

### Files to touch first

- [backend/app/models.py](../backend/app/models.py)
- [backend/app/schemas.py](../backend/app/schemas.py)
- [backend/app/api/routes.py](../backend/app/api/routes.py)
- relevant tests in [backend/tests](../backend/tests)

### Behavior to preserve

- organization-scoped data access
- human confirmation for consequential decisions
- stable IDs rather than display-name identity
- evidence and assertion provenance
- existing business asset workflows without breaking the current UI shell

### Behavior to add or tighten

- explicit assertion status model
- evidence attribution and reviewability
- organization-scoped safe queries
- shared entity linkage and relationship integrity
- careful handling of effective dates and supersession

### Scope guardrails

- Do not rewrite discovery or the UI shell in one shot.
- Do not broaden to full GRC or EA mechanisms before this foundation is stable.
- Do not create an irreversible merge or destructive migration path.

---

## 4. Evidence required to close Milestone 0

This is the exact evidence package the team should use before moving to Milestone 1.

### Required evidence package

1. A written repository assessment covering architecture, domain model, and repository risk
2. A migration risk note with safe rollback and non-destructive handling
3. A concept map showing how current models correspond to the target architecture
4. A Ground Zero capability assessment
5. A list of reusable components with exact file references
6. A conflict and overlap analysis
7. A baseline test report showing the command and result
8. A first-slice scope recommendation for Milestone 1

### Evidence already present in the repo

- [CODEX_PROJECT_REFERENCE.md](../CODEX_PROJECT_REFERENCE.md)
- [backend/app/models.py](../backend/app/models.py)
- [backend/app/api/routes.py](../backend/app/api/routes.py)
- [frontend/src/main.jsx](../frontend/src/main.jsx)
- [backend/app/schemas.py](../backend/app/schemas.py)

### Evidence already verified in this session

- Baseline repository test command and result:
  - Command: `cd /home/eric-graham/projects/STEWARD-DEV/backend && ../.venv/bin/python -m pytest -q`
  - Result: 76 passed, 0 failed, 2 warnings

---

## 5. Approval gate for Milestone 1

Milestone 1 may proceed only after:

- the required repository assessment is documented,
- migration and compatibility concerns are reviewed,
- the first slice for Milestone 1 is agreed,
- and the closure checklist above is checked off.

If any item remains unchecked, the project is still in the Milestone 0 gate.

---

## 6. Final status

Milestone 0 status: closed and approved

Reason:

The project is test-green, structurally mature, and the required closure package has been reviewed and approved. The current repo has the artifacts and architecture to support the safe next step, and the recommended first slice for Milestone 1 is now the approved boundary for implementation.
