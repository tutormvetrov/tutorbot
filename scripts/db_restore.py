#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import os
import subprocess
import sys
from pathlib import Path

from ops_common import (
    get_service_name,
    get_systemd_scope,
    is_bot_running,
    load_project_env,
    run_command,
    require_env,
)


RESET_PUBLIC_SCHEMA_SQL = """DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO CURRENT_USER;
GRANT ALL ON SCHEMA public TO public;
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore TutorBot PostgreSQL backup.")
    parser.add_argument("backup_path", help="Path to .sql, .sql.gz, .dump or .backup file.")
    return parser


def _psql_command(pg_host: str, pg_port: str, pg_user: str, database: str) -> list[str]:
    return [
        "psql",
        "--host",
        pg_host,
        "--port",
        pg_port,
        "--username",
        pg_user,
        "--set",
        "ON_ERROR_STOP=1",
        database,
    ]


def _run_psql_with_text(command: list[str], env: dict[str, str], sql_text: str) -> int:
    result = run_command(
        command,
        input=sql_text,
        text=True,
        env=env,
        check=False,
    )
    return result.returncode


def _run_psql_with_stream(command: list[str], env: dict[str, str], source) -> int:
    result = run_command(
        command,
        stdin=source,
        env=env,
        check=False,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = load_project_env()
    backup_path = Path(args.backup_path).expanduser().resolve()

    if not backup_path.exists():
        print(f"backup file not found: {backup_path}")
        return 1

    if str(os.getenv("TUTORBOT_ALLOW_RESTORE", "0")).strip() != "1":
        print("set TUTORBOT_ALLOW_RESTORE=1 to confirm database restore")
        return 1

    pg_user = require_env("PGUSER")
    pg_password = require_env("PGPASSWORD")
    database = require_env("DATABASE")
    pg_host = require_env("PGHOST")
    pg_port = require_env("PGPORT")
    env = os.environ.copy()
    env["PGPASSWORD"] = pg_password
    service_name = get_service_name()
    systemd_scope = get_systemd_scope()

    if is_bot_running(root, service_name=service_name, systemd_scope=systemd_scope) and str(
        os.getenv("TUTORBOT_ALLOW_LIVE_RESTORE", "0")
    ).strip() != "1":
        print(
            "refusing to restore while tutorbot is running; stop the service first or set "
            "TUTORBOT_ALLOW_LIVE_RESTORE=1"
        )
        return 1

    psql_command = _psql_command(pg_host, pg_port, pg_user, database)

    if str(os.getenv("TUTORBOT_SKIP_PRE_RESTORE_BACKUP", "0")).strip() != "1":
        backup_result = subprocess.run(
            [sys.executable, str(root / "scripts" / "db_backup.py")],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if backup_result.returncode != 0:
            sys.stdout.write(backup_result.stdout)
            sys.stderr.write(backup_result.stderr)
            return backup_result.returncode

    suffixes = backup_path.suffixes
    is_custom_dump = backup_path.suffix in {".dump", ".backup"}
    is_gzip_sql = suffixes[-2:] == [".sql", ".gz"] or backup_path.suffix == ".gz"

    if is_custom_dump:
        result = run_command(
            [
                "pg_restore",
                "--host",
                pg_host,
                "--port",
                pg_port,
                "--username",
                pg_user,
                "--dbname",
                database,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--single-transaction",
                str(backup_path),
            ],
            env=env,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
    else:
        if _run_psql_with_text(psql_command, env, RESET_PUBLIC_SCHEMA_SQL) != 0:
            return 1
        if is_gzip_sql:
            with gzip.open(backup_path, "rb") as payload:
                if _run_psql_with_stream(psql_command, env, payload) != 0:
                    return 1
        else:
            with backup_path.open("rb") as payload:
                if _run_psql_with_stream(psql_command, env, payload) != 0:
                    return 1

    print("restore completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
