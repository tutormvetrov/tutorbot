import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from aiogram.fsm.storage.base import StorageKey

from utils.fsm_storage import JsonFileStorage
from utils.text_utils import extract_student_name
from utils.ui_text import build_help_text


class JsonFileStorageTest(unittest.IsolatedAsyncioTestCase):
    async def test_storage_persists_state_and_data_between_instances(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "fsm.json"
            key = StorageKey(
                bot_id=1,
                chat_id=10,
                user_id=20,
                thread_id=None,
                business_connection_id=None,
                destiny="default",
            )

            storage = JsonFileStorage(path)
            await storage.set_state(key, "Registration:waiting_for_age")
            await storage.set_data(key, {"full_name": "Иван Петров", "age": 16})

            restored = JsonFileStorage(path)
            self.assertEqual(await restored.get_state(key), "Registration:waiting_for_age")
            self.assertEqual(await restored.get_data(key), {"full_name": "Иван Петров", "age": 16})


class CopyHelpersTest(unittest.TestCase):
    def test_extract_student_name_strips_age_suffixes(self):
        self.assertEqual(extract_student_name("Анна Петрова (14)"), "Анна Петрова")
        self.assertEqual(extract_student_name("Анна Петрова, 14"), "Анна Петрова")

    def test_help_text_uses_current_site_wording(self):
        text = build_help_text()
        self.assertIn("Сайт и материалы", text)
        self.assertNotIn("Авторский сайт", text)


if __name__ == "__main__":
    unittest.main()
