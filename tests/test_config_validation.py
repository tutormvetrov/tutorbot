import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from utils import config_validation


class RuntimeConfigValidationTest(unittest.TestCase):
    def test_collect_runtime_config_issues_accepts_minimal_valid_config_without_google(self):
        with patch.multiple(
            config,
            BOT_TOKEN="123456:token",
            ADMIN_ID=1,
            PGUSER="postgres",
            PGPASSWORD="secret",
            DATABASE="tutorbot",
            PGHOST="localhost",
            PGPORT="5432",
            GOOGLE_CALENDAR_ID="",
            GOOGLE_CREDENTIALS_FILE="/home/deploy/.secrets/tutorbot/credentials.json",
            TUTORBOT_ROOT=ROOT,
            TUTORBOT_SERVICE_NAME="tutorbot",
            TUTORBOT_SYSTEMD_SCOPE="system",
            TUTORBOT_BACKUP_DIR=ROOT / "backups",
        ):
            with patch.dict(os.environ, {"GOOGLE_CALENDAR_ID": "", "GOOGLE_CREDENTIALS_FILE": ""}, clear=False):
                issues = config_validation.collect_runtime_config_issues()
        self.assertEqual(issues, [])

    def test_collect_runtime_config_issues_rejects_placeholder_google_calendar(self):
        with patch.multiple(
            config,
            BOT_TOKEN="123456:token",
            ADMIN_ID=1,
            PGUSER="postgres",
            PGPASSWORD="secret",
            DATABASE="tutorbot",
            PGHOST="localhost",
            PGPORT="5432",
            GOOGLE_CALENDAR_ID="your_calendar_id@group.calendar.google.com",
            GOOGLE_CREDENTIALS_FILE="/tmp/missing-credentials.json",
            TUTORBOT_ROOT=ROOT,
            TUTORBOT_SERVICE_NAME="tutorbot",
            TUTORBOT_SYSTEMD_SCOPE="system",
            TUTORBOT_BACKUP_DIR=ROOT / "backups",
        ):
            with patch.dict(
                os.environ,
                {
                    "GOOGLE_CALENDAR_ID": "your_calendar_id@group.calendar.google.com",
                    "GOOGLE_CREDENTIALS_FILE": "/tmp/missing-credentials.json",
                },
                clear=False,
            ):
                issues = config_validation.collect_runtime_config_issues()

        self.assertTrue(any("placeholder" in issue for issue in issues))
        self.assertTrue(any("does not exist" in issue for issue in issues))

    def test_assert_runtime_config_raises_human_readable_error(self):
        with patch.multiple(
            config,
            BOT_TOKEN="",
            ADMIN_ID=0,
            PGUSER="",
            PGPASSWORD="",
            DATABASE="",
            PGHOST="",
            PGPORT="not-a-port",
            GOOGLE_CALENDAR_ID="",
            GOOGLE_CREDENTIALS_FILE="",
            TUTORBOT_ROOT=ROOT / "missing",
            TUTORBOT_SERVICE_NAME="",
            TUTORBOT_SYSTEMD_SCOPE="broken",
            TUTORBOT_BACKUP_DIR=ROOT / "missing" / "backups",
        ):
            with self.assertRaises(RuntimeError) as ctx:
                config_validation.assert_runtime_config()

        text = str(ctx.exception)
        self.assertIn("Invalid runtime configuration:", text)
        self.assertIn("BOT_TOKEN", text)
        self.assertIn("PGPORT", text)
        self.assertIn("TUTORBOT_SYSTEMD_SCOPE", text)


if __name__ == "__main__":
    unittest.main()
