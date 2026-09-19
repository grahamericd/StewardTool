#!/usr/bin/env bash
# Install the nightly PostgreSQL backup timer for this host and checkout.
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_USER="${BACKUP_USER:-${SUDO_USER:-$USER}}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo BACKUP_USER=$BACKUP_USER $0" >&2
  exit 1
fi

if ! id -nG "$BACKUP_USER" | tr ' ' '\n' | grep -qx docker; then
  echo "WARNING: $BACKUP_USER is not in the docker group; the backup will fail." >&2
fi

for unit in ai-data-steward-backup.service ai-data-steward-backup-failed.service; do
  sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__BACKUP_USER__|$BACKUP_USER|g" \
    "$PROJECT_DIR/deploy/systemd/$unit" > "$UNIT_DIR/$unit"
done
cp "$PROJECT_DIR/deploy/systemd/ai-data-steward-backup.timer" "$UNIT_DIR/ai-data-steward-backup.timer"

systemctl daemon-reload
systemctl enable --now ai-data-steward-backup.timer

echo "Installed. Next run:"
systemctl list-timers ai-data-steward-backup.timer --no-pager
