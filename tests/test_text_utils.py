import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.text_utils import normalize_language, parse_age


class TextUtilsTest(unittest.TestCase):
    def test_normalize_language_recognizes_english(self):
        language, is_known = normalize_language("хочу учить English")
        self.assertEqual(language, "Английский")
        self.assertTrue(is_known)

    def test_parse_age_understands_words_and_digits(self):
        self.assertEqual(parse_age("двадцать три года"), 23)
        self.assertEqual(parse_age("16"), 16)


if __name__ == "__main__":
    unittest.main()
