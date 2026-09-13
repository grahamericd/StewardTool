#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE=".env.production"
ENV_TEMPLATE=".env.production.example"

say() { printf '\n%s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available."
command -v python3 >/dev/null 2>&1 || fail "python3 is required."

if [ ! -f "$ENV_TEMPLATE" ]; then
  fail "$ENV_TEMPLATE is missing."
fi

if [ -f "$ENV_FILE" ]; then
  say "An existing $ENV_FILE was found."
  read -r -p "Keep it and skip environment creation? [Y/n]: " keep_env
  keep_env="${keep_env:-Y}"
  case "$keep_env" in
    Y|y) create_env="no" ;;
    *) fail "Fresh install stopped to avoid overwriting existing production configuration." ;;
  esac
else
  create_env="yes"
fi

if [ "$create_env" = "yes" ]; then
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  say "AI Data Steward fresh-install setup"
  echo "This creates a local production-shaped configuration."
  echo "You can add the real domain later in Stage 4.4d settings."

  read -r -p "Organization name [AI Data Steward Pilot]: " ORG_NAME
  ORG_NAME="${ORG_NAME:-AI Data Steward Pilot}"

  read -r -p "Organization code [PILOT]: " ORG_CODE
  ORG_CODE="${ORG_CODE:-PILOT}"

  read -r -p "Initial administrator email: " ADMIN_EMAIL
  [ -n "$ADMIN_EMAIL" ] || fail "Administrator email is required."

  read -r -p "Initial administrator display name: " ADMIN_NAME
  [ -n "$ADMIN_NAME" ] || fail "Administrator name is required."

  POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')"
  AUTH_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

  python3 - "$ENV_FILE" "$POSTGRES_PASSWORD" "$AUTH_SECRET_KEY" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
postgres_password = sys.argv[2]
auth_secret = sys.argv[3]

text = path.read_text()
replacements = {
    "POSTGRES_PASSWORD=CHANGE_ME_LONG_RANDOM_DATABASE_PASSWORD": f"POSTGRES_PASSWORD={postgres_password}",
    "AUTH_SECRET_KEY=CHANGE_ME_AT_LEAST_32_RANDOM_CHARACTERS": f"AUTH_SECRET_KEY={auth_secret}",
    "TESTGEN_MODE=real": "TESTGEN_MODE=mock",
}
for old, new in replacements.items():
    text = text.replace(old, new)

path.write_text(text)
PY

  printf '%s\n' "$ORG_NAME" > .fresh_install_org_name
  printf '%s\n' "$ORG_CODE" > .fresh_install_org_code
  printf '%s\n' "$ADMIN_EMAIL" > .fresh_install_admin_email
  printf '%s\n' "$ADMIN_NAME" > .fresh_install_admin_name

  chmod 600 .fresh_install_org_name .fresh_install_org_code .fresh_install_admin_email .fresh_install_admin_name

  say "Generated local production secrets."
  echo "The generated database password and signing key were written directly to $ENV_FILE."
  echo "They were not printed to the terminal."
fi

say "Validating production configuration..."
python3 scripts/check_production_hardening.py "$ENV_FILE"

say "Building and starting the production-shaped stack..."
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml up --build -d

say "Waiting for containers to become healthy..."
for attempt in $(seq 1 40); do
  if ./scripts/ops_status.sh http://localhost:8080 >/tmp/ai-data-steward-fresh-install-status.log 2>&1; then
    cat /tmp/ai-data-steward-fresh-install-status.log
    break
  fi
  if [ "$attempt" -eq 40 ]; then
    cat /tmp/ai-data-steward-fresh-install-status.log || true
    echo
    echo "The stack did not become healthy in time."
    echo "Run:"
    echo "  docker compose --env-file $ENV_FILE -f docker-compose.prod.yml ps"
    echo "  docker compose --env-file $ENV_FILE -f docker-compose.prod.yml logs --tail=120 backend frontend edge"
    exit 1
  fi
  sleep 3
done

if [ -f .fresh_install_admin_email ]; then
  ADMIN_EMAIL="$(cat .fresh_install_admin_email)"
  ADMIN_NAME="$(cat .fresh_install_admin_name)"
  ORG_CODE="$(cat .fresh_install_org_code)"
  ORG_NAME="$(cat .fresh_install_org_name)"

  say "Creating the initial administrator."
  echo "You will be prompted to enter the administrator password twice."
  docker compose --env-file "$ENV_FILE" \
    -f docker-compose.prod.yml \
    exec backend \
    python -m app.bootstrap_admin \
      --email "$ADMIN_EMAIL" \
      --name "$ADMIN_NAME" \
      --org-code "$ORG_CODE" \
      --org-name "$ORG_NAME"

  rm -f .fresh_install_org_name .fresh_install_org_code .fresh_install_admin_email .fresh_install_admin_name
fi

say "Creating the first verified database backup..."
./scripts/backup_postgres.sh
./scripts/verify_backup.sh

say "Fresh install complete."
echo
echo "Open:"
echo "  http://localhost:8080"
echo
echo "Next recommended actions:"
echo "  1. Sign in with the administrator account you just created."
echo "  2. Create a Steward user from User Administration."
echo "  3. Configure TestGen only after the base install is confirmed working."
echo "  4. Configure your purchased domain/HTTPS when ready."
