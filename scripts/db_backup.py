#!/usr/bin/env python3
from __future__ import annotations

import gzip
import os
import subprocess
import sys
from datetime import datetime, timezone

from ops_common import load_project_env, popen_command, require_env, resolve_path


def main(argv: list[str] | None = None) -> int:
    del argv
    root = load_project_env()

    pg_user = require_env("PGUSER")
    pg_password = require_env("PGPASSWORD")
    database = require_env("DATABASE")
    pg_host = require_env("PGHOST")
    pg_port = require_env("PGPORT")

    backup_dir = resolve_path(os.getenv("TUTORBOT_BACKUP_DIR", root / "backups"), root)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_path = backup_dir / f"{database}_{timestamp}.sql.gz"
    env = os.environ.copy()
    env["PGPASSWORD"] = pg_password
    command = [
        "pg_dump",
        "--host",
        pg_host,
        "--port",
        pg_port,
        "--username",
        pg_user,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        database,
    ]

    try:
        process = popen_command(
            command,
            stdout=subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        print("pg_dump not found", file=sys.stderr)
        return 1

    try:
        with gzip.open(target_path, "wb") as compressed:
            assert process.stdout is not None
            for chunk in iter(lambda: process.stdout.read(65536), b""):
                compressed.write(chunk)
    finally:
        if process.stdout is not None:
            process.stdout.close()

    if process.wait() != 0:
        target_path.unlink(missing_ok=True)
        return process.returncode or 1

    print(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
