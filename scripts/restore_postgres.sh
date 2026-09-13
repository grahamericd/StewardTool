#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 BACKUP_FILE"
  exit 2
fi

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "FAIL: backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "WARNING: This will replace the AI Data Steward PostgreSQL database."
printf "Type RESTORE to continue: "
read answer
if [ "$answer" != "RESTORE" ]; then
  echo "Restore cancelled."
  exit 1
fi

echo "Stopping application services..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop backend frontend edge

echo "Validating backup before restore..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_restore --list < "$BACKUP_FILE" >/dev/null

echo "Dropping and recreating database..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -U "$POSTGRES_USER" \
    -d postgres \
    -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$POSTGRES_DB'\'' AND pid <> pg_backend_pid();" \
    -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";" \
    -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"'

echo "Restoring backup..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    --exit-on-error' < "$BACKUP_FILE"

echo "Starting application services..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d backend frontend edge

echo "Restore completed. Run:"
echo "  ./scripts/ops_status.sh http://localhost:8080"
