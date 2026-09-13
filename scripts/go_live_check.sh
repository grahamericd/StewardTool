#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BASE_URL="${1:-http://localhost:8080}"

pass() { echo "PASS: $*"; }
warn() { echo "WARN: $*"; }
fail() { echo "FAIL: $*" >&2; FAILED=1; }

FAILED=0

echo "AI Data Steward — Stage 4.4h go-live check"
echo "Environment: $ENV_FILE"
echo "Base URL: $BASE_URL"
echo

if [ ! -f "$ENV_FILE" ]; then
  echo "FAIL: $ENV_FILE not found"
  exit 1
fi

echo "=== 1. Production configuration ==="
if python3 scripts/check_production_hardening.py "$ENV_FILE"; then
  pass "production configuration check passed"
else
  fail "production configuration check failed"
fi
echo

echo "=== 2. Compose validation ==="
if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null; then
  pass "Compose file validates"
else
  fail "Compose validation failed"
fi
echo

echo "=== 3. Operational health ==="
if ./scripts/ops_status.sh "$BASE_URL"; then
  pass "operational health passed"
else
  fail "operational health failed"
fi
echo

echo "=== 4. Network boundary ==="
if ./scripts/verify_network_hardening.sh "$BASE_URL"; then
  pass "network hardening passed"
else
  fail "network hardening failed"
fi
echo

echo "=== 5. Backup verification ==="
if ./scripts/verify_backup.sh; then
  pass "latest backup verified"
else
  fail "backup verification failed"
fi
echo

echo "=== 6. Authentication boundary ==="
auth_cfg_status="$(curl -sS -o /tmp/ads_auth_cfg.json -w "%{http_code}" "$BASE_URL/api/auth/config" || true)"
if [ "$auth_cfg_status" = "200" ]; then
  pass "public auth configuration endpoint reachable"
else
  fail "/api/auth/config returned HTTP $auth_cfg_status"
fi

me_status="$(curl -sS -o /tmp/ads_me.json -w "%{http_code}" "$BASE_URL/api/me" || true)"
if [ "$me_status" = "401" ]; then
  pass "protected /api/me rejects unauthenticated access"
else
  fail "/api/me expected 401, got $me_status"
fi
echo

echo "=== 7. Public deployment checks ==="
PUBLIC_APP_URL="$(grep '^PUBLIC_APP_URL=' "$ENV_FILE" | cut -d= -f2- || true)"
APP_SITE_ADDRESS="$(grep '^APP_SITE_ADDRESS=' "$ENV_FILE" | cut -d= -f2- || true)"
HTTP_PORT="$(grep '^HTTP_PORT=' "$ENV_FILE" | cut -d= -f2- || true)"
HTTPS_PORT="$(grep '^HTTPS_PORT=' "$ENV_FILE" | cut -d= -f2- || true)"

case "$PUBLIC_APP_URL" in
  http://localhost*|http://127.0.0.1*|"")
    warn "PUBLIC_APP_URL is still local. This is fine for local validation, not public go-live."
    ;;
  https://*)
    pass "PUBLIC_APP_URL uses HTTPS"
    ;;
  *)
    fail "PUBLIC_APP_URL must use HTTPS for public deployment"
    ;;
esac

case "$APP_SITE_ADDRESS" in
  http://localhost*|http://127.0.0.1*|"")
    warn "APP_SITE_ADDRESS is still local."
    ;;
  *)
    pass "APP_SITE_ADDRESS is configured for a named site"
    ;;
esac

if [ "${HTTP_PORT:-}" = "80" ] && [ "${HTTPS_PORT:-}" = "443" ]; then
  pass "public ports are configured as 80/443"
else
  warn "HTTP/HTTPS ports are ${HTTP_PORT:-unset}/${HTTPS_PORT:-unset}; expected 80/443 for public go-live"
fi
echo

echo "=== 8. Secret exposure reminder ==="
echo "Manual confirmation required before public go-live:"
echo "  - rotate AUTH_SECRET_KEY if it has ever been exposed"
echo "  - rotate POSTGRES_PASSWORD if it has ever been exposed"
echo "  - rotate TestGen OAuth client secret and refresh token if exposed"
echo "  - confirm .env.production is chmod 600"
echo "  - confirm backups exist off-host"
echo

if [ "$FAILED" -ne 0 ]; then
  echo "GO-LIVE RESULT: NOT READY"
  exit 1
fi

echo "GO-LIVE RESULT: TECHNICAL CHECKS PASSED"
echo "Review the manual items above before public exposure."
