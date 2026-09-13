#!/usr/bin/env sh
set -eu

COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"

echo "Validating Compose..."
$COMPOSE config >/dev/null

echo "Checking published ports..."
ports="$($COMPOSE ps --format json 2>/dev/null || true)"
# Use docker inspect for a robust service-by-service check.
for service in db backend frontend; do
  cid="$($COMPOSE ps -q "$service")"
  if [ -z "$cid" ]; then
    echo "FAIL: $service container is not running"
    exit 1
  fi
  published="$(docker inspect -f '{{json .NetworkSettings.Ports}}' "$cid")"
  case "$published" in
    *'"HostPort"'*)
      echo "FAIL: $service unexpectedly publishes a host port: $published"
      exit 1
      ;;
    *)
      echo "PASS: $service has no published host ports"
      ;;
  esac
done

edge_id="$($COMPOSE ps -q edge)"
if [ -z "$edge_id" ]; then
  echo "FAIL: edge container is not running"
  exit 1
fi

echo "PASS: only the edge is intended to publish host ports"
echo "Checking HTTP edge..."
./scripts/verify_edge.sh "${1:-http://localhost:8080}"
