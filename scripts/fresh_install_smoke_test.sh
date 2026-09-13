#!/usr/bin/env sh
set -eu

BASE_URL="${1:-http://localhost:8080}"

echo "Running fresh-install smoke test..."
./scripts/ops_status.sh "$BASE_URL"
./scripts/verify_network_hardening.sh "$BASE_URL"
./scripts/verify_backup.sh

status="$(curl -sS -o /tmp/ads_auth_config.json -w "%{http_code}" "$BASE_URL/api/auth/config")"
if [ "$status" != "200" ]; then
  echo "FAIL: /api/auth/config returned HTTP $status"
  exit 1
fi

echo "PASS: auth configuration endpoint is reachable"
echo "Fresh-install smoke test passed."
