# AI Data Steward — Go-Live Checklist

Use this as the final operator checklist.

## Technical

- [ ] continuous integration is green on the deployed commit
- [ ] `cd backend && python -m pytest -q` passes
- [ ] `./scripts/check_production_hardening.py .env.production` passes
- [ ] `docker compose ... config` passes
- [ ] all four containers are healthy
- [ ] `/health` returns 200
- [ ] unauthenticated `/api/me` returns 401
- [ ] only Caddy publishes host ports
- [ ] latest PostgreSQL backup verifies
- [ ] off-host backup copy exists

## Security

- [ ] `.env.production` is mode 600
- [ ] `AUTH_SECRET_KEY` has been rotated if exposed
- [ ] `POSTGRES_PASSWORD` has been rotated if exposed
- [ ] TestGen OAuth client secret has been rotated if exposed
- [ ] TestGen refresh token has been rotated if exposed
- [ ] no production secrets are committed to Git
- [ ] firewall exposes only required public ports

## Domain

- [ ] DNS points to the production server
- [ ] public URL uses HTTPS
- [ ] Caddy obtained a valid certificate
- [ ] HTTP redirects to HTTPS
- [ ] `TRUSTED_HOSTS` contains the real domain
- [ ] `CORS_ORIGINS` contains the real HTTPS origin

## Application

- [ ] administrator can sign in
- [ ] Steward can sign in
- [ ] first-login password change works
- [ ] User Administration works for ORG_ADMIN
- [ ] Steward cannot see User Administration
- [ ] Steward Home loads
- [ ] My Information loads
- [ ] My Next Steps loads
- [ ] review/publishing workflow loads
- [ ] quality workflow loads
- [ ] TestGen works if enabled

## Operations

- [ ] manual backup succeeds
- [ ] backup verification succeeds
- [ ] restore procedure has been reviewed
- [ ] log rotation is enabled
- [ ] `ops_status.sh` passes
- [ ] daily backup schedule is enabled (`sudo ./scripts/install_backup_timer.sh`) or explicitly deferred
- [ ] `systemctl list-timers ai-data-steward-backup.timer` shows a next run
- [ ] operator knows where logs and backups are stored

## Final command

```bash
./scripts/go_live_check.sh https://your-domain.example
```

Do not publicly launch until failures are resolved and manual security items are confirmed.
