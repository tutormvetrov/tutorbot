#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops_common import is_bot_running, load_project_env


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.config_validation import assert_runtime_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TutorBot runtime healthcheck.")
    parser.add_argument(
        "--mode",
        choices=("local", "runtime"),
        default="runtime",
        help="runtime is strict and expects a running bot; local skips process checks when unsupported.",
    )
    return parser


def _check_ops_status(ops_path: Path) -> int:
    if not ops_path.exists():
        print("ops status file missing")
        return 1

    data = json.loads(ops_path.read_text(encoding="utf-8"))
    status = str(data.get("status", "unknown"))
    if status not in {"running", "starting"}:
        print(f"ops status is {status}")
        return 1

    updated_at = data.get("updated_at")
    if updated_at:
        stamp = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - stamp > timedelta(minutes=20):
            print("ops status is stale")
            return 1
    return 0


def run_healthcheck(mode: str = "runtime", *, skip_validation: bool = False) -> int:
    root = load_project_env()
    if not skip_validation:
        assert_runtime_config(mode=mode)

    running = is_bot_running(root)
    if mode == "runtime" and not running:
        print("bot process not running")
        return 1

    ops_status = root / "data" / "ops_status.json"
    metrics = root / "data" / "runtime_metrics.jsonl"
    should_check_runtime_files = mode == "runtime" or running or ops_status.exists() or metrics.exists()

    if should_check_runtime_files:
        result = _check_ops_status(ops_status)
        if result != 0:
            return result

        if metrics.exists() and metrics.stat().st_size == 0:
            print("runtime metrics file is empty")
            return 1

    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return run_healthcheck(mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
