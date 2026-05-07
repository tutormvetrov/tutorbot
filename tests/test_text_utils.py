import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.text_utils import derive_preferred_name, normalize_language, parse_age


class TextUtilsTest(unittest.TestCase):
    def test_normalize_language_recognizes_english(self):
        language, is_known = normalize_language("хочу учить English")
        self.assertEqual(language, "Английский")
        self.assertTrue(is_known)

    def test_parse_age_understands_words_and_digits(self):
        self.assertEqual(parse_age("двадцать три года"), 23)
        self.assertEqual(parse_age("16"), 16)


class DerivePreferredNameTest(unittest.TestCase):
    def test_first_last(self):
        self.assertEqual(derive_preferred_name("Иван Петров"), "Иван")

    def test_last_first_inverted(self):
        self.assertEqual(derive_preferred_name("Безруков Иван"), "Иван")

    def test_single_token(self):
        self.assertEqual(derive_preferred_name("Полина"), "Полина")

    def test_three_tokens_official_order(self):
        self.assertEqual(derive_preferred_name("Иванов Иван Иванович"), "Иван")

    def test_ambiguous_two_tokens_defaults_to_first(self):
        self.assertEqual(derive_preferred_name("Роман Алексей"), "Роман")

    def test_empty_string(self):
        self.assertEqual(derive_preferred_name(""), "")

    def test_none(self):
        self.assertEqual(derive_preferred_name(None), "")

    def test_clear_male_surname_first(self):
        # «Безруков Иван» -> "Иван" — original bug from production
        self.assertEqual(derive_preferred_name("Безруков Иван"), "Иван")

    def test_female_surname_clear_form_first(self):
        # «Сорокин Алексей» — male surname -ин — admin order, name comes second
        self.assertEqual(derive_preferred_name("Сорокин Алексей"), "Алексей")


if __name__ == "__main__":
    unittest.main()
