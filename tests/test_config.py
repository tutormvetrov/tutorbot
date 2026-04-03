import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data.config import is_internal_test_account, normalize_person_name


class ConfigHelpersTest(unittest.TestCase):
    def test_normalize_person_name_normalizes_whitespace_and_yo(self):
        self.assertEqual(
            normalize_person_name("  ЕЛИЗАВЕТА   ЗАНКЕВИЧ  "),
            "елизавета занкевич",
        )

    def test_internal_account_detects_known_test_user(self):
        self.assertTrue(
            is_internal_test_account(
                full_name="Елизавета Занкевич",
                username="eliza_znkv",
            )
        )

    def test_internal_account_detects_by_telegram_id(self):
        self.assertTrue(
            is_internal_test_account(
                full_name="Любой Пользователь",
                telegram_id=389264815,
            )
        )


if __name__ == "__main__":
    unittest.main()
