#!/usr/bin/env sh
set -eu

BASE_URL="${1:-http://localhost:8080}"

echo "Checking $BASE_URL/health"
curl -fsS "$BASE_URL/health"
echo
echo "Checking unauthenticated protection at $BASE_URL/api/me"
status="$(curl -sS -o /tmp/ads_me_check.txt -w "%{http_code}" "$BASE_URL/api/me")"
if [ "$status" != "401" ]; then
  echo "Expected HTTP 401 from /api/me, got $status"
  cat /tmp/ads_me_check.txt
  exit 1
fi
echo "Protected endpoint correctly returned 401."
echo "Edge validation passed."
