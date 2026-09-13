# AI Data Steward — Fresh Install Guide

This guide is for a new self-hosted installation of AI Data Steward on a Linux host with Docker.

## Fast path

From the project directory:

```bash
./scripts/preflight_install.sh
./scripts/fresh_install.sh
```

The installer will:

- create `.env.production` if one does not exist
- generate a random PostgreSQL password
- generate a random authentication signing key
- default TestGen to `mock` so optional integrations cannot block first startup
- build and start the production-shaped Docker stack
- wait for the services to become healthy
- prompt you to create the initial organization administrator
- create and verify the first PostgreSQL backup

The generated secrets are written directly into `.env.production` and are not printed.

## After installation

Open:

```text
http://localhost:8080
```

Sign in with the administrator account created during installation.

Then use:

**Administration → User Administration**

to create additional users and assign roles.

## Recommended order after first login

1. Confirm the Steward Home loads.
2. Add one Steward user.
3. Confirm the Steward cannot see User Administration.
4. Add or discover a test information asset.
5. Configure TestGen only after the base application works.
6. Configure the public domain and HTTPS.
7. Run the smoke test:

```bash
./scripts/fresh_install_smoke_test.sh http://localhost:8080
```

## Existing installation

`fresh_install.sh` will not overwrite an existing `.env.production`.

If `.env.production` already exists, it asks whether to keep it. It will not silently replace production secrets.

## TestGen

A new installation starts with:

```env
TESTGEN_MODE=mock
```

This is deliberate.

After the application is healthy, copy the validated TestGen settings into `.env.production` and change:

```env
TESTGEN_MODE=real
```

Then recreate the backend:

```bash
docker compose --env-file .env.production   -f docker-compose.prod.yml   up -d --force-recreate backend
```

## Production domain

For a real domain, update `.env.production` with the domain settings documented in `.env.domain.example`, then restart the stack.

## Backups

Create a backup:

```bash
./scripts/backup_postgres.sh
```

Verify:

```bash
./scripts/verify_backup.sh
```

Operational status:

```bash
./scripts/ops_status.sh http://localhost:8080
```

## Security

Before exposing the service publicly:

- rotate any credentials that have ever been exposed
- keep `.env.production` at permission mode `600`
- only expose ports 80/443 on the final server
- keep database/backend/frontend host ports closed
- ensure a verified backup exists
- move backup copies off-host
