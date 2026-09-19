# Continuous integration

`github-actions-ci.yml` is the workflow for this repository. It is kept here
rather than at `.github/workflows/ci.yml` only because the account that opened
this pull request does not hold the GitHub `workflow` OAuth scope, which is
required to push files under `.github/workflows/`.

To enable it, move the file and commit:

```bash
mkdir -p .github/workflows
git mv docs/ci/github-actions-ci.yml .github/workflows/ci.yml
git commit -m "Enable CI"
git push
```

## What it runs

| Job | Purpose |
| --- | --- |
| `backend` | `pytest` against SQLite |
| `backend-postgres` | `pytest` against PostgreSQL 16, because the timezone defect only reproduced on SQLite |
| `audit` | `pip-audit` on the Python pins and `npm audit` on the lockfile |
| `frontend` | `npm ci` and `vite build` from the lockfile |
| `images` | validates the production compose file and builds both container images |

The test suite had been failing for four released versions before this was
added, which is the reason it exists.
