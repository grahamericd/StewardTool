# AI Data Steward --- Project Reference for Codex

## 1. Mission

AI Data Steward is a guided, human-in-the-loop data-governance platform
for people who understand their business information but may not
understand formal data governance.

The core problem is that when organizations ask employees, "What data do
you have?", people often answer with software-system names rather than
actual information assets. They may also fail to recognize PDFs,
spreadsheets, folders, emails, images, SharePoint content, database
tables, extracts, APIs, and similar information as governable data.

The product therefore starts with systems, tools, and business
information users already recognize and progressively guides them toward
identifying, documenting, governing, improving, reviewing, and
publishing actual data assets.

The intended progression is:

    Organization
        → familiar systems/tools
        → business information
        → data assets
        → resources/locations
        → business understanding and metadata
        → ownership/governance
        → quality expectations/evidence
        → stewardship tasks and human decisions
        → review/approval
        → immutable release snapshot
        → DCAT representation
        → CKAN/enterprise catalog publication

The product should feel like a guided stewardship assistant, not a
metadata spreadsheet or database administration tool.

## 2. Product principles

### Meet users where they are

Prefer questions such as:

-   What system or tool does your team use?
-   What information does your team work with?
-   Where does that information live?
-   What does it help your team do?
-   Who can answer business questions about it?
-   How often does it change?
-   Is this the official source?
-   What would make this information untrustworthy?

Do not require ordinary stewards to understand terms such as DCAT
distribution, lineage node, metadata schema, authoritative data source,
or DQV measurement before they can contribute useful governance
information.

### Guided governance, not CRUD cataloging

The primary UI should remain approachable, polished, and appropriate for
government executives, data leaders, and business stewards. Advanced
technical information can exist, but should normally be secondary to
guided workflows.

### Human-in-the-loop

AI may suggest candidate assets, descriptions, search terms, metadata,
quality rules, hygiene findings, remediation, and next actions. It
should not silently make consequential governance decisions. Humans
remain responsible for confirming official sources, accepting or
rejecting recommendations, approving governance information,
dispositioning quality issues, and approving publication.

### Federated governance

AI Data Steward is not intended to centralize all enterprise data. It
should govern and catalog information where it lives and support systems
of systems, commercial products, databases, document repositories, APIs,
files, and other sources.

### Working state is different from approved state

Publication should use an approved release/snapshot rather than blindly
publishing the current mutable working record. The organization should
be able to determine what was approved, who approved it, when, what
metadata and quality evidence existed, and what was published.

## 3. Users and roles

Current role concepts include:

-   STEWARD
-   APPROVER
-   ORG_ADMIN
-   ENTERPRISE_ADMIN

Seed/demo identities include:

    steward@demo.gov
    approver@demo.gov
    admin@demo.gov
    enterprise@demo.gov

Role and organization boundaries must be enforced in the backend, not
merely by hiding frontend controls.

## 4. Technology stack

Frontend: - React - Vite - JavaScript/JSX - frontend/src/main.jsx
contains much of the current application - frontend/src/api.js contains
API helper logic - frontend/src/styles.css contains application
styling - nginx serves the production frontend

Backend: - Python - FastAPI - SQLAlchemy - Pydantic - PostgreSQL 16 -
Uvicorn

Infrastructure: - Docker / Docker Compose - Caddy production
edge/reverse proxy - nginx frontend container - Cloudflare in front of
production - dedicated persistent PostgreSQL Docker volume

Integrations: - DataKitchen TestGen for technical data-quality
execution/evidence - DCAT mapping - CKAN publisher architecture - mock
catalog publication for controlled testing

## 5. Important repository areas

    backend/
        app/
            api/
                routes.py
                auth_routes.py
                admin_routes.py
            integrations/testgen/client.py
            services/
                publication.py
                publisher.py
                quality_orchestrator.py
                snapshot.py
                task_service.py
                profile_validator.py
                dcat_mapper.py
            auth.py
            config.py
            db.py
            models.py
            schemas.py
            seed.py
        tests/
        pytest.ini
        requirements.txt
        requirements-dev.txt

    frontend/
        src/main.jsx
        src/api.js
        src/styles.css
        Dockerfile
        nginx.conf
        package.json

    deploy/
        caddy/Caddyfile
        systemd/

    scripts/
        check_production_hardening.py
        install_backup_timer.sh
        restore_postgres.sh
        secret_rotation_check.sh
        verify_backup.sh

    docs/ci/
        README.md
        github-actions-ci.yml

    docker-compose.yml
    docker-compose.prod.yml
    PRODUCTION_DEPLOYMENT_GUIDE.md
    GO_LIVE_CHECKLIST.md
    README.md

This list is representative, not authoritative. Inspect the repository
before making changes.

## 6. Domain concepts

The current backend includes concepts around:

-   organizations
-   application users
-   organization memberships and roles
-   systems
-   data assets
-   data resources
-   asset/resource relationships
-   asset metadata
-   governance requirements
-   quality profiles
-   quality rules
-   quality results
-   quality issues/findings
-   quality-engine resources
-   stewardship tasks
-   publication/release records
-   authentication credentials

backend/app/models.py is authoritative for the current model.

## 7. Guided stewardship workflows

### My Data Landscape

The landing/dashboard experience should help users understand their
known information landscape and stewardship state rather than merely
expose database records.

### Discover Your Data

Discovery begins from systems/tools familiar to users and progressively
identifies actual information/data assets. A system is not automatically
a dataset.

A representative demo is the Business Licensing System, whose purpose is
to manage professional licenses, applications, payments, disciplinary
actions, and uploaded PDF applications. This demonstrates that one
system can contain multiple information assets and resource types.

### Data Asset 360

The asset view brings together business understanding, metadata,
governance, quality, resources, review, and publication. Exact
tab/section labels may evolve; inspect current frontend code.

### Understand It

This workflow collects plain-language business context such as: -
business definition - business area/theme - search/discovery terms -
update frequency - business contact

The user should answer understandable questions while the application
creates structured metadata.

### Where It Lives

Records resources/locations and supports identifying an official or
authoritative source.

### Govern It

Guides users toward missing governance requirements and decisions.

### Quality

Presents quality evidence and integrates TestGen findings.

### Review & Maintain

Supports periodic review so stewardship is an ongoing lifecycle.

### Share & Publish

Approved information can become a release/snapshot and flow through the
catalog publishing architecture.

## 8. Structured contact metadata --- recent regression fix

Manual acceptance testing after the independent code review found a
frontend crash because contact metadata could be structured while the
frontend assumed it was always a string and called contactPoint.trim().

Existing metadata could look like:

    {
      "name": "Licensing Data Steward",
      "email": "licensing@example.gov"
    }

The fix supports structured contacts while retaining backward
compatibility with older string contacts.

The user-facing experience should remain simple:

    Person, team, or office: Licensing Data Steward
    Email or shared mailbox: licensing@example.gov

The backend should preserve structured metadata suitable for
standards/catalog mapping. Do not regress to string-only contact
handling.

Relevant areas: - frontend/src/main.jsx - backend/app/api/routes.py -
backend/app/schemas.py - backend/app/services/dcat_mapper.py

Relevant commit: 8bdac2a Fix structured contact handling in
understanding workflow

## 9. Metadata and standards direction

Metadata should be gathered through business-friendly interactions and
normalized internally.

Existing concepts include: - business definition - business owner -
theme/business area - keyword/search terms - update frequency -
contact - authoritative source - classification - resources - quality
assessment

DCAT mapping includes concepts such as: - dct:identifier - dct:title -
dct:description - dct:publisher - dcat:theme - dcat:keyword -
dct:accrualPeriodicity - dcat:contactPoint - dcat:distribution -
dcat:DataService - DQV quality measurements

Standards compliance should be an outcome of guided stewardship, not a
prerequisite for using the product.

## 10. Data quality and DataKitchen TestGen

The intended separation is:

    TestGen / quality engine
        → technical tests and observations
        → quality results/findings
        → AI Data Steward
        → business/governance interpretation
        → stewardship task
        → human decision/remediation/acceptance

AI Data Steward should not merely display a score and should not try to
become a TestGen clone.

Current quality concepts include completeness, validity, uniqueness,
consistency, timeliness, and overall quality.

A quality finding should help the steward understand: - what failed -
why it matters - what asset/resource is affected - supporting evidence -
expected action - responsible party - disposition/remediation state

TestGen configuration may include:

    TESTGEN_MODE
    TESTGEN_BASE_URL
    TESTGEN_AUTH_MODE
    TESTGEN_TOKEN
    TESTGEN_OAUTH_CLIENT_ID
    TESTGEN_OAUTH_CLIENT_SECRET
    TESTGEN_OAUTH_REFRESH_TOKEN
    TESTGEN_PROJECT_CODE
    TESTGEN_TABLE_GROUP_ID
    TESTGEN_TEST_SUITE_ID

Never hardcode secrets or tokens.

The production Caddy proxy currently has a read timeout around 620
seconds to support synchronous TestGen polling.

## 11. Stewardship tasks

Governance should produce actionable work rather than only completeness
percentages.

Tasks may arise from missing governance information, quality findings,
periodic review, or other governance conditions.

The system should increasingly answer "What should I do next?" and
explain: - what is missing/wrong - why it matters - what action to
take - where to take it - what completion means

## 12. Publication architecture

Desired lifecycle:

    Working asset
        → readiness/governance checks
        → submit
        → review
        → approve
        → release/snapshot
        → DCAT mapping
        → catalog publication

Relevant code: - backend/app/services/publication.py -
backend/app/services/publisher.py - backend/app/services/snapshot.py -
backend/app/services/dcat_mapper.py

Catalog configuration includes:

    CATALOG_PUBLISHER
    CKAN_BASE_URL
    CKAN_API_KEY
    CKAN_OWNER_ORG

Do not make uncontrolled live CKAN calls from automated tests.

## 13. Authentication and security

An independent code review resulted primarily in security,
authentication, production-hardening, and defensive-reliability
improvements. It was not a major redesign of product functionality.

Authentication modes include: - demo - local - oidc

Demo mode can trust an X-User-Email identity header and must never be
treated as safe for a public production deployment.

Local authentication includes/hardens: - local credentials - password
hashing - bearer-token sessions - temporary passwords - forced password
changes - password resets - session expiration - login
throttling/failure handling - account-enumeration resistance

OIDC support exists for external identity-provider integration.

Backend authorization must enforce organization and role boundaries.

The review also hardened trusted hosts, CORS, production configuration,
database configuration, Docker build context, nginx/Caddy behavior,
secrets checks, backup/restore tooling, API failure handling, and
session cleanup.

Do not casually undo these controls while implementing product features.

## 14. Production network architecture

Production is Cloudflare-fronted:

    Browser
        → HTTPS / Cloudflare
        → origin
        → Caddy :80
        → frontend:8080 (nginx)
             ├─ React
             └─ /api → backend:8000
                         → PostgreSQL

Production Caddy intentionally uses: auto_https off :80

The production Compose edge binding is intentionally loopback-only:
127.0.0.1:\${HTTP_PORT:-8080}:80

Do not blindly replace this with direct public :443 exposure or
Caddy-managed ACME without understanding the Cloudflare deployment.

Current Caddy hardening/features should preserve: - removal of Server
header - X-Content-Type-Options - X-Frame-Options - Referrer-Policy -
Permissions-Policy - CSP including object-src 'none' - HSTS - JSON
access logging - \~620-second TestGen proxy read timeout

## 15. DEV and PROD isolation

Production checkout: \~/projects/STEWARD

Observed production PostgreSQL volume: steward_ads_prod_pgdata

Production containers use names similar to: steward-db-1
steward-backend-1 steward-frontend-1 steward-edge-1

Development checkout: \~/projects/STEWARD-DEV

Development has been run with: docker compose -p steward-dev -f
docker-compose.dev.yml ...

Observed DEV ports: PostgreSQL 127.0.0.1:5434 → 5432 Backend
127.0.0.1:8001 → 8000 Frontend localhost:5173

Observed DEV database volume: steward-dev_ads_stage3_pgdata

NON-NEGOTIABLE: Never point development/tests at the production database
volume. Do not deploy by copying DEV files directly over PROD. Changes
should flow through Git and controlled deployment.

## 16. Source-control/release history

The independent review was tested on branch: Claude_review

Important commits: dac0f9d Fix the defects found in the independent code
review 414dab0 Stage the CI workflow outside .github/workflows 0b3debf
Merge pull request #2 from clj2289/fix/review-findings-2026-09-14
8bdac2a Fix structured contact handling in understanding workflow

Reviewed branch merged into main at: 1c06fe4 Merge reviewed and
acceptance-tested improvements

Known release tag: v4.4.1

The production Cloudflare-specific configuration was subsequently
intended to become official Git configuration. Verify current history
and git status rather than assuming that final housekeeping commit/tag
was completed.

Always begin with: git status git branch --show-current git log
--oneline --decorate -10

## 17. Test baseline

Immediately before promotion, backend tests reported: 64 passed 2
warnings 0 failures

Test modules included: - test_quality_stage34.py -
test_quality_stage35.py - test_review_fixes.py - test_stage2.py -
test_stage3.py - test_stage351_catalog_context.py -
test_stage352_hygiene_workbench.py - test_stage353_evidence.py -
test_stage353a_testgen_payload.py - test_stage353b_regex_import.py -
test_stage41_expert_review.py - test_stage42d_official_source.py -
test_stage42f_periodic_review.py - test_stage43a_understanding.py -
test_stage44b_auth.py - test_stage44c_user_admin.py -
test_stage44e2_database_url.py - test_stage44e_hardening.py -
test_stage4_task_guidance.py

Frontend production build also passed with: cd frontend npm run build

Required regression discipline: cd backend && pytest cd frontend && npm
run build

Add/update tests for behavioral changes. Do not delete tests merely to
obtain a green suite unless the underlying requirement intentionally
changed.

## 18. CI status

A proposed GitHub Actions workflow exists under:
docs/ci/github-actions-ci.yml

It was intentionally staged outside: .github/workflows/

Do not assume GitHub Actions CI is active. Review it before enabling it.

## 19. Backup and recovery

The review added/improved PostgreSQL backup verification, restore
tooling, systemd backup service, and failure handling.

Before production database/schema/deployment changes: 1. create a
database backup; 2. verify PostgreSQL can read it; 3. preserve relevant
production configuration; 4. know the rollback commit/tag; 5. never
destroy the production volume.

A verified pre-v4.4.1 backup was created during deployment under
\~/steward-backups/, but inspect the filesystem rather than assuming a
specific timestamp/path.

## 20. Lessons from acceptance testing

A successful build is not enough. The reviewed branch passed automated
tests and frontend compilation, but manual testing still found the
structured-contact crash.

Use three gates: automated backend tests + frontend production build +
manual workflow acceptance

UI workflow progression must depend on API success. Do not show
"complete" after a failed save.

Existing metadata may use legacy shapes. Before changing a metadata
representation, inspect seed data, serialization, schemas, API behavior,
and persisted-data compatibility.

## 21. Near-term product direction

The security/code-review cycle is complete enough. Future work should
primarily advance data-governance functionality unless a concrete
security need is identified.

High-value directions include:

### Guided metadata

Deepen plain-language capture of business meaning, owner/steward,
subject/domain, authoritative source, sensitivity/classification,
retention expectations, update cadence, business contact, search
language, criticality, intended consumers, and sharing restrictions.

### Discovery

Improve System → Information → Asset → Resource. One system may manage
many assets; one asset may have multiple resources/distributions.

### AI assistance

Use AI for candidate asset identification, metadata suggestions,
plain-language explanations, governance-gap identification, quality
expectations/rules, evidence interpretation, remediation
recommendations, and task guidance. Suggestions should be reviewable and
attributable.

### Governance evidence

Record why, when, and by whom governance decisions were established.

### Data quality

Deepen TestGen integration while preserving: quality engine detects → AI
Data Steward governs/responds.

### Enterprise catalog

Continue standards-based output and CKAN interoperability.

### Relationships/context

Help users understand information relationships across systems and
organizations without requiring centralized physical data storage.

## 22. What this product must NOT become

Do not turn AI Data Steward into:

1.  A generic CRUD catalog where users fill 30 unfamiliar metadata
    fields.
2.  A centralized data-ingestion platform.
3.  A TestGen clone.
4.  An AI autopilot with no human accountability.
5.  Primarily a security/authentication project.

Security is important, but the core differentiator is guided governance
for non-experts.

## 23. Coding-agent operating rules

Before changing code: 1. Run git status and identify branch/commit. 2.
Read relevant implementation and tests. 3. Trace frontend → API → schema
→ service/model. 4. Check legacy/persisted representations. 5. Explain
broad architectural changes before making them.

While changing code: 1. Make the smallest coherent change. 2. Preserve
backward compatibility where reasonable. 3. Never bypass backend
authorization. 4. Never hardcode secrets. 5. Never point DEV/tests at
PROD. 6. Preserve guided/nontechnical UX. 7. Add tests for defects/new
behavior. 8. Do not silently change publication/governance semantics. 9.
Avoid unrelated refactors. 10. Preserve Cloudflare production behavior
unless deployment is intentionally redesigned.

After changing code: 1. Run backend pytest. 2. Run frontend npm build.
3. Identify the manual workflow requiring acceptance testing. 4.
Summarize files changed, behavior changed, tests, migration/deployment
implications, manual test steps, and known risks.

## 24. Production safety rules

Unless explicitly asked to deploy production, do NOT: - run docker
compose down on PROD; - delete Docker volumes; - run destructive SQL
against PROD; - overwrite .env.production; - reset production
credentials; - expose PostgreSQL publicly; - replace Cloudflare origin
behavior with direct public Caddy TLS; - copy DEV DB into PROD; -
force-push main; - rewrite release tags; - copy uncommitted DEV files
into PROD.

Preferred release path:

    DEV implementation
        → automated tests
        → frontend build
        → manual acceptance in isolated DEV
        → commit/push
        → merge
        → backup PROD
        → verify backup
        → controlled production deployment
        → container health checks
        → public smoke test

## 25. Design standard for every new feature

For each feature ask:

User question --- What understandable question is the steward trying to
answer?

Governance meaning --- What governance concept does the answer
represent?

Structured representation --- How should it be stored consistently?

Standards mapping --- Does it map to DCAT, DQV, CKAN, or another
standard?

Evidence --- How do we know the answer is trustworthy?

Accountability --- Who supplied/approved it and when?

Lifecycle --- How is it reviewed and updated?

Action --- Can a missing/problematic answer generate useful stewardship
work?

Publication --- Should it appear in an approved release/catalog record?

This pattern is central to the product.

## 26. Example of the desired abstraction

The steward sees:

    How does this information change?
    ○ Continuously as work occurs
    ○ Daily
    ○ Weekly
    ○ Monthly
    ○ Quarterly
    ○ Annually
    ○ Only when a business event happens
    ○ I'm not sure

The platform can internally normalize/map that to
dct:accrualPeriodicity.

The steward sees:

    Who can answer business questions about this information?

The platform can create a structured contact suitable for
dcat:contactPoint.

Plain business language → governed structured metadata is one of the
application's most important design patterns.

## 27. Definition of success

AI Data Steward succeeds when someone who knows the business but knows
little about formal data governance can use it and leave the
organization with:

-   discoverable information assets;
-   useful business definitions;
-   ownership/accountability;
-   known authoritative sources;
-   structured metadata;
-   governance evidence;
-   quality expectations/results;
-   actionable stewardship tasks;
-   review history;
-   approved release snapshots;
-   standards-based catalog records.

The user should not need to understand the metadata standard to produce
metadata that conforms to it.

## 28. First actions for a new Codex session

Start in the isolated development checkout, not PROD:

    cd ~/projects/STEWARD-DEV
    git status
    git branch --show-current
    git log --oneline --decorate -10

Then inspect at least: - README.md - backend/app/models.py -
backend/app/schemas.py - backend/app/api/routes.py -
backend/app/services/task_service.py -
backend/app/services/quality_orchestrator.py -
backend/app/services/snapshot.py - backend/app/services/dcat_mapper.py -
backend/app/services/publisher.py - frontend/src/main.jsx -
frontend/src/api.js - frontend/src/styles.css - backend/tests/

The repository is the source of truth if it differs from this handoff.

Before coding, summarize: 1. current implementation relevant to the
requested feature; 2. proposed design; 3. files expected to change; 4.
tests that prove it works; 5. migration/backward-compatibility concerns.

## 29. One-paragraph mission statement

AI Data Steward is a guided, human-in-the-loop data-governance platform
for people who understand their business information but may not
understand formal data governance. It starts with systems and
information users recognize, guides them toward identifying real data
assets and resources, captures business meaning and governance decisions
through plain-language workflows, integrates technical quality evidence
such as DataKitchen TestGen, creates actionable stewardship work,
preserves review/approval history, and publishes approved structured
metadata through standards such as DCAT and catalogs such as CKAN. The
product should hide unnecessary governance complexity without
sacrificing governance rigor.
