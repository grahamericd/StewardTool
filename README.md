# AI Data Steward — Stage 3

Stage 3 keeps everything validated in Stages 1–2 and makes **data quality actionable** by integrating DataKitchen TestGen as the quality engine beneath the AI Data Steward experience.

## What Stage 3 proves

```text
Organization → System → Data Asset → Resource
                        ↓
                Metadata & Governance
                        ↓
             DataKitchen TestGen adapter
                  ↓             ↓
              Profiling       Test Runs
                  ↓             ↓
             Quality Health   Failures
                        ↓
                  Quality Issue
                        ↓
                 Stewardship Task
                        ↓
                     Guide Me
                        ↓
        Bad data / Valid exception /
        Expectation change / Expert review
                        ↓
                 Resolve & audit
                        ↓
               Approve → DCAT → CKAN
```

The steward never needs to use TestGen terminology. The UI says **Assess Data Quality**, **Suggested quality expectations**, **Quality issues**, and **Guide Me**.

## TestGen integration modes

Stage 3 intentionally ships with two modes.

### `TESTGEN_MODE=mock` — default

A deterministic TestGen-shaped adapter exercises the entire workflow without requiring TestGen to be installed first. Use this to validate Stage 3 immediately.

It demonstrates:
- profile run
- TestGen-origin quality score
- suggested expectations
- rule approval/rejection
- test execution
- failed checks
- automatic quality issues
- automatic Stewardship Inbox tasks
- guided human decision and task resolution

### `TESTGEN_MODE=real`

The backend uses TestGen's documented REST run workflow:

- `POST /api/v1/table-groups/{table_group_id}/profiling-runs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/profiling-runs/{job_id}`
- `POST /api/v1/test-suites/{test_suite_id}/test-runs`
- `GET /api/v1/test-runs/{job_id}`

Set:

```env
TESTGEN_MODE=real
TESTGEN_BASE_URL=http://host.docker.internal:8530
TESTGEN_TOKEN=<bearer token if your TestGen instance requires one>
```

Then open Data Asset 360 → Data Quality → **TestGen connection mapping** and enter the Table Group ID and Test Suite ID for the resource.

## First test — no TestGen install required

Stage 3 uses host port **5433** for its PostgreSQL container because many development machines already run PostgreSQL on 5432.

From the project root:

```bash
docker compose down
docker compose up --build
```

In another terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Open:

```text
http://localhost:5173
```

### Stage 3 test sequence

1. Open **Data Asset 360** → **Data Quality**.
2. Select the structured `APPLICATION` resource.
3. Click **Assess Data Quality**.
4. Confirm the latest quality profile says `TESTGEN` and suggested expectations appear.
5. Approve **ZIP Code should use a recognized 5-digit or ZIP+4 format** and **Application ID is required**.
6. Click **Run Approved Checks**.
7. Confirm quality issues appear and the score changes.
8. Open **Stewardship Inbox** and confirm the failed checks became Quality tasks.
9. Return to Data Quality and click **Guide Me** on an issue.
10. Record one of the four decisions:
    - The data is incorrect
    - This is a valid exception
    - The quality expectation needs to change
    - I need expert review
11. Confirm resolved work disappears from the active Inbox.
12. Re-test the existing publication workflow through immutable release → DCAT JSON-LD → catalog publisher.

## Installing TestGen for the real integration

DataKitchen's current recommended Mac/Linux installation uses its installer and supports Docker Compose or a pip/embedded-PostgreSQL mode. Install TestGen **separately** from AI Data Steward so TestGen remains a replaceable technical engine rather than becoming the system of record.

A helper script is included at:

```text
scripts/install_testgen.sh
```

After installation:

1. Connect TestGen to the target PostgreSQL/database with read-only permissions.
2. Create a Table Group around the table(s) you want to assess.
3. Run profiling once in TestGen.
4. Create a Test Suite.
5. If your edition supports REST access tokens, create one and put it in `TESTGEN_TOKEN`.
6. Switch AI Data Steward to `TESTGEN_MODE=real`.
7. Map the AI Data Steward resource to the TestGen Table Group / Test Suite IDs.

## Important architecture boundary

- **AI Data Steward** = catalog, governance, human decisions, tasks, guidance, audit, publication.
- **TestGen** = technical profiling, test execution, monitoring, quality scoring.
- **CKAN/DCAT** = enterprise catalog publication and discovery.

AI Data Steward stores TestGen object IDs in `quality_engine_resources`; the core catalog model never depends on TestGen-specific tables.

## New Stage 3 tables

- `quality_engine_resources`
- `quality_issues`
- `quality_decisions`

Existing Stage 2 tables remain intact.

## Stage 4 candidates

- synchronize detailed TestGen column profiles and hygiene findings using the expanded REST API
- map AI Data Steward approved business expectations into TestGen test definitions/import API
- TestGen monitor integration for freshness, volume, schema and metric anomalies
- Connect the existing AI Data Steward Rule Registry as the canonical governed expectation model
- remediation workflow / assignment to source-system owners
- trend charts and recurring quality schedules
- MCP-assisted Steward Copilot
