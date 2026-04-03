#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.config_validation import assert_runtime_config


def main() -> int:
    assert_runtime_config()
    print("config ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
