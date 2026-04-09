#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${TUTORBOT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
export TUTORBOT_ROOT="$ROOT"

PYTHON_BIN="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi

exec "$PYTHON_BIN" "$ROOT/scripts/db_restore.py" "$@"
