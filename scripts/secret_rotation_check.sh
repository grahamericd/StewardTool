#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.production}"

if [ ! -f "$ENV_FILE" ]; then
  echo "FAIL: $ENV_FILE not found"
  exit 1
fi

echo "AI Data Steward — secret rotation readiness"
echo
echo "This script never prints secret values."
echo

for key in \
  AUTH_SECRET_KEY \
  POSTGRES_PASSWORD \
  TESTGEN_OAUTH_CLIENT_SECRET \
  TESTGEN_OAUTH_REFRESH_TOKEN
do
  value="$(grep "^${key}=" "$ENV_FILE" | cut -d= -f2- || true)"
  if [ -z "$value" ]; then
    echo "WARN: $key is empty or missing"
  else
    echo "PRESENT: $key (length ${#value})"
  fi
done

mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo unknown)"
if [ "$mode" = "600" ]; then
  echo "PASS: $ENV_FILE permissions are 600"
else
  echo "WARN: $ENV_FILE permissions are $mode; recommended 600"
fi

echo
echo "Rotation notes:"
echo "  AUTH_SECRET_KEY:"
echo "    Generate locally: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
echo "    Updating it invalidates existing login tokens."
echo
echo "  POSTGRES_PASSWORD:"
echo "    Change PostgreSQL first with \\password steward, then update .env.production."
echo "    Then RECREATE the backend so it re-reads the env file:"
echo "      docker compose --env-file .env.production -f docker-compose.prod.yml up -d backend"
echo "    'docker compose restart' keeps the old environment and will crash-loop."
echo
echo "  TestGen OAuth:"
echo "    Rotate at the TestGen/OAuth provider, then update .env.production."
echo "    Do not paste the values into chat, Git, or documentation."
