from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils import google_calendar


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _command_path(bin_dir: Path, name: str) -> Path:
    return bin_dir / (f"{name}.cmd" if os.name == "nt" else name)


def _write_command(bin_dir: Path, name: str, posix_body: str, windows_body: str | None = None) -> Path:
    path = _command_path(bin_dir, name)
    _write_executable(path, windows_body if os.name == "nt" else posix_body)
    return path


class GoogleCalendarSyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_events_paginates_all_pages(self):
        calls: list[dict] = []

        class _Executable:
            def __init__(self, payload: dict):
                self.payload = payload

            def execute(self):
                return self.payload

        class _EventsApi:
            def list(self, **kwargs):
                calls.append(kwargs)
                if kwargs.get("pageToken") == "page-2":
                    return _Executable({"items": [{"id": "evt-2"}]})
                return _Executable({"items": [{"id": "evt-1"}], "nextPageToken": "page-2"})

        class _Service:
            def events(self):
                return _EventsApi()

        with (
            patch("utils.google_calendar._build_service", return_value=_Service()),
            patch("utils.google_calendar.config.GOOGLE_CALENDAR_ID", "calendar@example.com"),
        ):
            events, pages_fetched = google_calendar._fetch_events(days_ahead=14)

        self.assertEqual([item["id"] for item in events], ["evt-1", "evt-2"])
        self.assertEqual(pages_fetched, 2)
        self.assertEqual(calls[0].get("pageToken"), None)
        self.assertEqual(calls[1].get("pageToken"), "page-2")

    async def test_sync_calendar_tracks_pages_and_deletes_only_after_full_snapshot(self):
        class FakeDB:
            def __init__(self):
                self.deleted_event_ids: list[str] = []

            async def get_all_students(self):
                return [
                    {"telegram_id": 101, "full_name": "Иван Петров"},
                    {"telegram_id": 102, "full_name": "Анна Соколова"},
                ]

            async def get_calendar_student_links(self):
                return []

            async def upsert_lesson_from_calendar(self, student_id, google_event_id, lesson_date):
                return "inserted"

            async def get_google_event_ids_in_window(self, days_ahead=60):
                return ["evt-1", "evt-2", "evt-stale"]

            async def delete_lessons_by_event_ids(self, event_ids):
                self.deleted_event_ids = list(event_ids)

        events = [
            {
                "id": "evt-1",
                "summary": "Урок с Иван Петров",
                "start": {"dateTime": "2026-04-10T10:00:00+03:00"},
            },
            {
                "id": "evt-2",
                "summary": "Урок с Анна Соколова",
                "start": {"dateTime": "2026-04-11T11:00:00+03:00"},
            },
        ]
        db = FakeDB()
        old_report_file = google_calendar.SYNC_REPORT_FILE

        with tempfile.TemporaryDirectory() as tmp_dir:
            google_calendar.SYNC_REPORT_FILE = Path(tmp_dir) / "calendar_sync_report.json"
            try:
                with patch("utils.google_calendar._fetch_events", return_value=(events, 2)):
                    report = await google_calendar.sync_calendar_to_db(db)
            finally:
                google_calendar.SYNC_REPORT_FILE = old_report_file

        self.assertTrue(report["fetch_complete"])
        self.assertEqual(report["pages_fetched"], 2)
        self.assertEqual(report["events_fetched"], 2)
        self.assertEqual(report["deleted"], 1)
        self.assertEqual(db.deleted_event_ids, ["evt-stale"])

    def test_match_student_from_title_supports_inflected_russian_name(self):
        event = {
            "summary": "Урок с Максимом Письменским общий английский онлайн"
        }
        students = [{
            "telegram_id": 348191634,
            "full_name": "Максим Письменский",
        }]

        student_id, reason = google_calendar._match_student_from_title(event, students)

        self.assertEqual(student_id, 348191634)
        self.assertEqual(reason, "title_full_name")


class OpsScriptsTest(unittest.TestCase):
    def _copy_script_to_temp_root(self, script_name: str, tmp_root: Path) -> Path:
        scripts_dir = tmp_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        destination = scripts_dir / script_name
        shutil.copy2(ROOT / "scripts" / script_name, destination)
        if os.name != "nt":
            destination.chmod(destination.stat().st_mode | stat.S_IXUSR)
        return destination

    def _copy_ops_scripts(self, tmp_root: Path, *script_names: str) -> dict[str, Path]:
        copied: dict[str, Path] = {}
        for script_name in {"ops_common.py", *script_names}:
            copied[script_name] = self._copy_script_to_temp_root(script_name, tmp_root)
        return copied

    def test_db_restore_refuses_live_restore_by_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            script = self._copy_ops_scripts(tmp_root, "db_restore.py", "db_backup.py")["db_restore.py"]
            backup_path = tmp_root / "backup.sql"
            backup_path.write_text("SELECT 1;\n", encoding="utf-8")
            bin_dir = tmp_root / "bin"
            bin_dir.mkdir()

            _write_command(
                bin_dir,
                "systemctl",
                "#!/usr/bin/env bash\n"
                "if [ \"$2\" = \"is-active\" ]; then exit 0; fi\n"
                "exit 0\n",
                "@echo off\r\n"
                "if \"%2\"==\"is-active\" exit /b 0\r\n"
                "exit /b 0\r\n",
            )

            env = {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "TUTORBOT_ALLOW_RESTORE": "1",
                "PGUSER": "postgres",
                "PGPASSWORD": "secret",
                "DATABASE": "tutorbot",
                "PGHOST": "localhost",
                "PGPORT": "5432",
            }
            result = subprocess.run(
                [sys.executable, str(script), str(backup_path)],
                cwd=tmp_root,
                env={**os.environ, **env},
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to restore while tutorbot is running", result.stdout + result.stderr)

    def test_db_restore_resets_public_schema_before_plain_sql_restore(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            script = self._copy_ops_scripts(tmp_root, "db_restore.py", "db_backup.py")["db_restore.py"]
            backup_path = tmp_root / "backup.sql"
            backup_path.write_text("CREATE TABLE demo(id integer);\n", encoding="utf-8")
            bin_dir = tmp_root / "bin"
            bin_dir.mkdir()
            psql_log = tmp_root / "psql.log"

            _write_command(bin_dir, "systemctl", "#!/usr/bin/env bash\nexit 1\n", "@echo off\r\nexit /b 1\r\n")
            _write_command(bin_dir, "pgrep", "#!/usr/bin/env bash\nexit 1\n", "@echo off\r\nexit /b 1\r\n")
            _write_command(
                bin_dir,
                "psql",
                "#!/usr/bin/env bash\n"
                "cat <<'MARKER' >> \"$PSQL_LOG\"\n"
                "---CALL---\n"
                "MARKER\n"
                "cat >> \"$PSQL_LOG\"\n",
                "@echo off\r\n"
                "echo ---CALL--- >> \"%PSQL_LOG%\"\r\n"
                "more >> \"%PSQL_LOG%\"\r\n",
            )

            env = {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "TUTORBOT_ALLOW_RESTORE": "1",
                "TUTORBOT_SKIP_PRE_RESTORE_BACKUP": "1",
                "PGUSER": "postgres",
                "PGPASSWORD": "secret",
                "DATABASE": "tutorbot",
                "PGHOST": "localhost",
                "PGPORT": "5432",
                "PSQL_LOG": str(psql_log),
            }
            result = subprocess.run(
                [sys.executable, str(script), str(backup_path)],
                cwd=tmp_root,
                env={**os.environ, **env},
                capture_output=True,
                text=True,
            )

            log_text = psql_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("DROP SCHEMA IF EXISTS public CASCADE;", log_text)
        self.assertIn("CREATE TABLE demo(id integer);", log_text)

    def test_db_backup_passes_clean_dump_flags(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            script = self._copy_ops_scripts(tmp_root, "db_backup.py")["db_backup.py"]
            bin_dir = tmp_root / "bin"
            bin_dir.mkdir()
            pg_dump_log = tmp_root / "pg_dump.log"
            backup_dir = tmp_root / "backups"

            _write_command(
                bin_dir,
                "pg_dump",
                "#!/usr/bin/env bash\n"
                "printf '%s\n' \"$@\" > \"$PG_DUMP_LOG\"\n"
                "printf 'CREATE TABLE demo(id integer);\\n'\n",
                "@echo off\r\n"
                "echo %* > \"%PG_DUMP_LOG%\"\r\n"
                "echo CREATE TABLE demo(id integer);\r\n",
            )

            env = {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "PGUSER": "postgres",
                "PGPASSWORD": "secret",
                "DATABASE": "tutorbot",
                "PGHOST": "localhost",
                "PGPORT": "5432",
                "PG_DUMP_LOG": str(pg_dump_log),
                "TUTORBOT_BACKUP_DIR": str(backup_dir),
            }
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=tmp_root,
                env={**os.environ, **env},
                capture_output=True,
                text=True,
            )

            dump_args = pg_dump_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("--clean", dump_args)
        self.assertIn("--if-exists", dump_args)
        self.assertTrue(result.stdout.strip().endswith(".sql.gz"))
