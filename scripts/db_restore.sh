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

BACKUP_PATH="${1:-}"
if [ -z "$BACKUP_PATH" ]; then
  echo "usage: $0 /path/to/backup.sql.gz"
  exit 1
fi

if [ ! -f "$BACKUP_PATH" ]; then
  echo "backup file not found: $BACKUP_PATH"
  exit 1
fi

if [ "${TUTORBOT_ALLOW_RESTORE:-0}" != "1" ]; then
  echo "set TUTORBOT_ALLOW_RESTORE=1 to confirm database restore"
  exit 1
fi

: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${DATABASE:?DATABASE is required}"
: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"

export PGPASSWORD

if [ "${TUTORBOT_SKIP_PRE_RESTORE_BACKUP:-0}" != "1" ]; then
  "$ROOT/scripts/db_backup.sh" >/dev/null
fi

case "$BACKUP_PATH" in
  *.gz)
    gzip -dc "$BACKUP_PATH" | psql \
      --host "$PGHOST" \
      --port "$PGPORT" \
      --username "$PGUSER" \
      --set ON_ERROR_STOP=1 \
      "$DATABASE"
    ;;
  *)
    psql \
      --host "$PGHOST" \
      --port "$PGPORT" \
      --username "$PGUSER" \
      --set ON_ERROR_STOP=1 \
      "$DATABASE" <"$BACKUP_PATH"
    ;;
esac

echo "restore completed"
