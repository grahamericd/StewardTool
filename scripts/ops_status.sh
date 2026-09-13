#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BASE_URL="${1:-http://localhost:8080}"

echo "=== AI Data Steward operational status ==="
echo
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
echo

echo "=== Edge health ==="
if curl -fsS "$BASE_URL/health"; then
  echo
  echo "PASS: public health endpoint is reachable"
else
  echo
  echo "FAIL: public health endpoint is not reachable"
  exit 1
fi

echo
echo "=== Container health ==="
failed=0
for service in db backend frontend edge; do
  cid="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q "$service")"
  if [ -z "$cid" ]; then
    echo "FAIL: $service is not running"
    failed=1
    continue
  fi
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
  case "$status" in
    healthy|running)
      echo "PASS: $service = $status"
      ;;
    *)
      echo "FAIL: $service = $status"
      failed=1
      ;;
  esac
done

echo
echo "=== Recent application errors ==="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs \
  --since=15m --no-color backend frontend edge 2>/dev/null \
  | grep -Ei 'ERROR|CRITICAL|Traceback|panic|fatal' \
  | tail -n 25 || echo "No recent error signatures found."

if [ "$failed" -ne 0 ]; then
  exit 1
fi

echo
echo "Operational status passed."
