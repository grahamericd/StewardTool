#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
  BACKUP_DIR="${BACKUP_DIR:-backups}"
  BACKUP_FILE="$(ls -1t "$BACKUP_DIR"/ai_data_steward_*.dump 2>/dev/null | head -n 1 || true)"
fi

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
  echo "FAIL: no backup file found"
  exit 1
fi

echo "Checking backup: $BACKUP_FILE"
test -s "$BACKUP_FILE"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_restore --list < "$BACKUP_FILE" >/dev/null

# A backup that verifies but is a month old is not a backup anyone can rely on.
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-36}"
if find "$BACKUP_FILE" -mmin "+$((MAX_AGE_HOURS * 60))" 2>/dev/null | grep -q .; then
  echo "FAIL: newest backup is older than ${MAX_AGE_HOURS}h. Is the nightly timer enabled?"
  echo "      scripts/install_backup_timer.sh installs it."
  exit 1
fi

echo "PASS: backup is recent, non-empty, and pg_restore can read its catalog"
