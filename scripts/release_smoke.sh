#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${TUTORBOT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

"$ROOT/.venv/bin/python" "$ROOT/scripts/validate_env.py"
"$ROOT/scripts/healthcheck.sh"

echo "release smoke ok"
