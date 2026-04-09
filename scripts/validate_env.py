#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.config_validation import assert_runtime_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate TutorBot runtime configuration.")
    parser.add_argument(
        "--mode",
        choices=("local", "runtime"),
        default="runtime",
        help="Validation strictness. Use runtime on the server and local for developer machines.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    assert_runtime_config(mode=args.mode)
    print("config ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
