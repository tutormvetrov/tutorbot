import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "config.py"


def load_config_module(env: dict[str, str]) -> object:
    saved_env = os.environ.copy()
    try:
        os.environ.update(env)
        spec = importlib.util.spec_from_file_location("tutorbot_config_under_test", CONFIG_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(saved_env)


class ConfigEnvTest(unittest.TestCase):
    def test_config_reads_env_values_and_composes_postgres_uri(self):
        module = load_config_module(
            {
                "BOT_TOKEN": "token-123",
                "ADMIN_ID": "42",
                "PGUSER": "alice",
                "PGPASSWORD": "secret",
                "DATABASE": "tutorbot",
                "PGHOST": "db.example.test",
                "PGPORT": "6543",
                "GOOGLE_CALENDAR_ID": "calendar@example.com",
                "GOOGLE_CREDENTIALS_FILE": "/tmp/credentials.json",
            }
        )

        self.assertEqual(module.BOT_TOKEN, "token-123")
        self.assertEqual(module.ADMIN_ID, 42)
        self.assertEqual(module.PGUSER, "alice")
        self.assertEqual(module.PGPASSWORD, "secret")
        self.assertEqual(module.DATABASE, "tutorbot")
        self.assertEqual(module.PGHOST, "db.example.test")
        self.assertEqual(module.PGPORT, "6543")
        self.assertEqual(module.POSTGRES_URI, "postgresql://alice:secret@db.example.test:6543/tutorbot")
        self.assertEqual(module.GOOGLE_CALENDAR_ID, "calendar@example.com")
        self.assertEqual(module.GOOGLE_CREDENTIALS_FILE, "/tmp/credentials.json")

    def test_teacher_info_loader_reads_json_and_falls_back_cleanly(self):
        module = load_config_module({})

        with tempfile.TemporaryDirectory() as tmpdir:
            info_path = Path(tmpdir) / "teacher_info.json"
            info_path.write_text(
                json.dumps(
                    {
                        "contacts": {"telegram": "@teacher"},
                        "requisites": {"rate": "3000 ₽"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            module._TEACHER_INFO_PATH = str(info_path)
            loaded = module.load_teacher_info()
            self.assertEqual(loaded["contacts"]["telegram"], "@teacher")
            self.assertEqual(loaded["requisites"]["rate"], "3000 ₽")

            info_path.write_text("{not valid json", encoding="utf-8")
            self.assertEqual(module.load_teacher_info(), {})

            info_path.unlink()
            self.assertEqual(module.load_teacher_info(), {})

    def test_internal_account_helpers_cover_known_test_identity(self):
        module = load_config_module({})

        self.assertTrue(module.is_internal_test_account_name("Лиза Занкевич"))
        self.assertTrue(module.is_internal_test_account(
            full_name="Любой Пользователь",
            username="eliza_znkv",
        ))
        self.assertTrue(module.is_internal_test_account(
            full_name="Любой Пользователь",
            telegram_id=389264815,
        ))
        self.assertFalse(module.is_internal_test_account(
            full_name="Иван Петров",
            username="ivan.petrov",
            telegram_id=123456,
        ))

    def test_runtime_validation_helpers_format_human_readable_output(self):
        from utils.config_validation import format_runtime_config_issues

        self.assertEqual(
            format_runtime_config_issues([]),
            "Runtime configuration is valid.",
        )
        self.assertEqual(
            format_runtime_config_issues(["one problem", "two problem"]),
            "Invalid runtime configuration:\n- one problem\n- two problem",
        )


if __name__ == "__main__":
    unittest.main()
