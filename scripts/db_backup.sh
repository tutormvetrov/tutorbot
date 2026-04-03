#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${TUTORBOT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ROOT/.env"
  set +a
fi

: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${DATABASE:?DATABASE is required}"
: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"

BACKUP_DIR="${TUTORBOT_BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET_PATH="${BACKUP_DIR%/}/${DATABASE}_${TIMESTAMP}.sql.gz"

export PGPASSWORD
pg_dump \
  --host "$PGHOST" \
  --port "$PGPORT" \
  --username "$PGUSER" \
  --no-owner \
  --no-privileges \
  "$DATABASE" | gzip -c >"$TARGET_PATH"

echo "$TARGET_PATH"
