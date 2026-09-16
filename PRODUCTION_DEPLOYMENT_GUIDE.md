# AI Data Steward — Production Deployment Guide

Version: 4.4h

This guide is the final deployment checklist for the self-hosted MVP.

## 1. What is included

The production-shaped stack contains:

```text
Internet / Browser
        |
        v
      Caddy
    ports 80/443
        |
        v
  Frontend Nginx
        |
        v
      FastAPI
        |
        v
    PostgreSQL
```

Only the Caddy edge should publish host ports.

## 2. Before public deployment

Complete these items before exposing the service to the Internet:

- production `.env.production` exists and is permission mode `600`
- `AUTH_MODE=local`
- `AUTH_SECRET_KEY` is long and random
- `POSTGRES_PASSWORD` is long and random
- exposed credentials from development/debugging have been rotated
- TestGen OAuth credentials are valid if `TESTGEN_MODE=real`
- at least one verified PostgreSQL backup exists
- at least one backup copy is stored off-host
- the production domain has DNS pointed to the server
- inbound TCP 80 and 443 reach the server
- PostgreSQL, FastAPI, and frontend ports are not publicly exposed

Run:

```bash
./scripts/secret_rotation_check.sh .env.production
```

This reports presence/length only and never prints secret values.

## 3. Domain and HTTPS

For a public host such as:

```text
steward.example.com
```

set:

```env
APP_SITE_ADDRESS=steward.example.com
HTTP_PORT=80
HTTPS_PORT=443
ACME_EMAIL=your-admin-email@example.com

PUBLIC_APP_URL=https://steward.example.com
CORS_ORIGINS=https://steward.example.com
TRUSTED_HOSTS=steward.example.com
```

Create the DNS A record pointing to the server's public IPv4 address.

Create an AAAA record only if public IPv6 is actually routed to the server.

Caddy will request and renew TLS automatically when DNS and inbound ports are correct.

## 4. Start the stack

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  up --build -d
```

Then:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  ps
```

All four services should remain up and healthy:

- db
- backend
- frontend
- edge

## 5. Run the final technical check

For local validation:

```bash
./scripts/go_live_check.sh http://localhost:8080
```

For the real public domain:

```bash
./scripts/go_live_check.sh https://steward.example.com
```

The script checks:

- production settings
- Docker Compose validity
- container health
- public `/health`
- internal network exposure
- latest backup readability
- auth boundary
- public HTTPS configuration

## 6. Initial administrator

A fresh installation should use:

```bash
./scripts/fresh_install.sh
```

For an established install, the bootstrap command remains available:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  exec backend \
  python -m app.bootstrap_admin \
  --email admin@example.com \
  --name "Administrator Name" \
  --org-code PILOT \
  --org-name "AI Data Steward Pilot"
```

Passwords are prompted securely and are not placed in shell history.

## 7. User administration

After signing in as `ORG_ADMIN`:

```text
Administration
  User Administration
```

Use the application to:

- create users
- assign roles
- reset temporary passwords
- deactivate/reactivate organization access

The bootstrap CLI should not be the normal day-to-day user-management tool.

## 8. TestGen

For first boot, `TESTGEN_MODE=mock` is acceptable.

When enabling real TestGen:

```env
TESTGEN_MODE=real
TESTGEN_BASE_URL=http://host.docker.internal:8530
TESTGEN_AUTH_MODE=oauth_refresh
TESTGEN_TOKEN=
TESTGEN_OAUTH_CLIENT_ID=<local secret>
TESTGEN_OAUTH_CLIENT_SECRET=<local secret>
TESTGEN_OAUTH_REFRESH_TOKEN=<local secret>
TESTGEN_PROJECT_CODE=DEFAULT
TESTGEN_TABLE_GROUP_ID=<validated table-group id>
TESTGEN_TEST_SUITE_ID=<validated test-suite id>
```

Then recreate the backend:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d --force-recreate backend
```

Never paste OAuth secrets into documentation, Git, screenshots, or chat.

After changing any secret in `.env.production`, **recreate** the affected
service rather than restarting it. `docker compose restart` reuses the
container's original environment:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d backend
```

## 9. Backups

Install the nightly timer (once per host):

```bash
sudo ./scripts/install_backup_timer.sh
```

This fills the systemd unit in with this host's user and project directory,
enables the timer, and prints when it next runs.

Create a backup now:

```bash
./scripts/backup_postgres.sh
```

Verify:

```bash
./scripts/verify_backup.sh
```

Restore:

```bash
./scripts/restore_postgres.sh backups/<backup-file>.dump
```

The restore takes its own safety backup before dropping anything and restarts
the application services if it fails partway.

A restore requires typing:

```text
RESTORE
```

Keep at least one backup copy off the application server.

## 10. Daily operations

Operational status:

```bash
./scripts/ops_status.sh https://steward.example.com
```

Logs:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  logs -f
```

Backend logs:

```bash
docker compose --env-file .env.production \
  -f docker-compose.prod.yml \
  logs -f backend
```

## 11. Firewall exposure

The host/network firewall should allow only what is required for the application:

```text
TCP 80
TCP 443
```

Do not publicly expose:

```text
5432 / PostgreSQL
8000 / FastAPI
8080 / internal frontend
8530 / TestGen API
```

If administrative SSH is required, restrict it according to the server's operating environment.

## 12. Rollback

Before every application upgrade:

```bash
./scripts/backup_postgres.sh
./scripts/verify_backup.sh
```

Then record the current Git commit/tag.

If an upgrade fails:

1. stop the application stack
2. restore the previous application version
3. rebuild the previous version
4. restore the database only if the upgrade changed data/schema in a way that is not backward-compatible
5. run the go-live check again

Do not automatically restore the database merely because an application container fails. Diagnose first.

## 13. Final go-live acceptance

Before calling the MVP production-ready, manually confirm:

- real domain loads over HTTPS
- browser shows a valid TLS certificate
- administrator can sign in
- Steward user can sign in
- Steward cannot see User Administration
- administrator can create/deactivate users
- Steward Home loads
- information inventory loads
- quality workflow loads
- TestGen integration works if enabled
- publication/review workflow loads
- a verified backup exists
- off-host backup copy exists
- exposed credentials have been rotated
- `./scripts/go_live_check.sh https://your-domain` passes

## 14. Stage 4.4 status

After 4.4h is validated, the self-hosted MVP hardening sequence is complete:

```text
4.4a  Production configuration
4.4b  Authentication & real users
4.4c  User / role administration
4.4d  HTTPS, domain & reverse proxy
4.4e  Secrets & network hardening
4.4f  Backup / restore / health / logging
4.4g  Fresh-install onboarding
4.4h  Production smoke-test & deployment guide
```

The application can then move from "development hardening" to normal pilot operations and incremental product development.
