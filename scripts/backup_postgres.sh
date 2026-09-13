#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if [ ! -f "$ENV_FILE" ]; then
  echo "FAIL: $ENV_FILE not found"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$BACKUP_DIR/ai_data_steward_${timestamp}.dump"
tmp_path="${backup_path}.tmp"

cleanup() {
  rm -f "$tmp_path"
}
trap cleanup EXIT INT TERM

echo "Creating PostgreSQL backup..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --format=custom \
    --no-owner \
    --no-privileges' > "$tmp_path"

if [ ! -s "$tmp_path" ]; then
  echo "FAIL: backup file is empty"
  exit 1
fi

mv "$tmp_path" "$backup_path"
chmod 600 "$backup_path"

echo "Verifying backup catalog..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_restore --list < "$backup_path" >/dev/null

find "$BACKUP_DIR" -type f -name 'ai_data_steward_*.dump' \
  -mtime "+$RETENTION_DAYS" -print -delete 2>/dev/null || true

echo "PASS: backup created and verified"
echo "$backup_path"
