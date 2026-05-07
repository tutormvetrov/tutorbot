"""
Утилиты для семантического разбора пользовательского ввода.
"""
import re

# ─── Language normalization ────────────────────────────────────────────────────

# Слова-шумы, которые убираем перед разбором
_NOISE = {
    "язык", "language", "lang", "учу", "изучаю", "хочу", "учить",
    "изучать", "занимаюсь", "заниматься", "изучение", "буду", "хотел",
    "хотела", "собираюсь", "я",
}

# Известные языки и их нормализованные формы
_LANGUAGE_MAP = {
    # Английский
    "английский": "Английский", "английском": "Английский",
    "английская": "Английский", "английского": "Английский",
    "английскому": "Английский", "английском": "Английский",
    "english": "Английский", "англ": "Английский", "eng": "Английский",
    # Французский
    "французский": "Французский", "французском": "Французский",
    "french": "Французский", "франц": "Французский", "fr": "Французский",
    "français": "Французский", "francais": "Французский",
    # Немецкий
    "немецкий": "Немецкий", "немецком": "Немецкий",
    "german": "Немецкий", "нем": "Немецкий",
    "deutsch": "Немецкий", "de": "Немецкий",
    # Испанский
    "испанский": "Испанский", "испанском": "Испанский",
    "spanish": "Испанский", "español": "Испанский",
    "espanol": "Испанский", "esp": "Испанский",
    # Итальянский
    "итальянский": "Итальянский", "итальянском": "Итальянский",
    "italian": "Итальянский", "italiano": "Итальянский",
    # Китайский
    "китайский": "Китайский", "китайском": "Китайский",
    "chinese": "Китайский", "кит": "Китайский",
    "mandarin": "Китайский", "中文": "Китайский",
    # Японский
    "японский": "Японский", "японском": "Японский",
    "japanese": "Японский", "яп": "Японский", "日本語": "Японский",
    # Корейский
    "корейский": "Корейский", "корейском": "Корейский",
    "korean": "Корейский", "кор": "Корейский", "한국어": "Корейский",
    # Португальский
    "португальский": "Португальский", "португальском": "Португальский",
    "portuguese": "Португальский", "português": "Португальский",
    "portugues": "Португальский",
    # Арабский
    "арабский": "Арабский", "арабском": "Арабский",
    "arabic": "Арабский", "arab": "Арабский",
    # Турецкий
    "турецкий": "Турецкий", "турецком": "Турецкий",
    "turkish": "Турецкий", "türkçe": "Турецкий",
    # Польский
    "польский": "Польский", "польском": "Польский",
    "polish": "Польский", "polski": "Польский",
    # Нидерландский
    "нидерландский": "Нидерландский", "голландский": "Голландский",
    "dutch": "Нидерландский", "nederlands": "Нидерландский",
}


def normalize_language(text: str) -> tuple[str, bool]:
    """
    Извлекает название языка из произвольного текста.
    Примеры: "английский язык", "хочу учить французский", "English" → нормализованное название.
    Возвращает (название, is_known) — is_known=True если язык из известного списка.
    """
    words = text.lower().split()
    # Сначала ищем известный язык
    for word in words:
        clean = word.strip(".,!?;:—-\"'")
        if clean in _LANGUAGE_MAP:
            return _LANGUAGE_MAP[clean], True
    # Откат: убираем шум и берём первое значимое слово
    meaningful = [
        w.strip(".,!?;:—-\"'")
        for w in words
        if w.strip(".,!?;:—-\"'") not in _NOISE
    ]
    if meaningful:
        return meaningful[0].capitalize(), False
    return text.strip().capitalize(), False


# ─── Age parsing ──────────────────────────────────────────────────────────────

_RU_UNITS = {
    "один": 1, "одного": 1, "одна": 1, "одну": 1,
    "два": 2, "две": 2, "двух": 2,
    "три": 3, "трёх": 3, "трех": 3,
    "четыре": 4, "четырёх": 4, "четырех": 4,
    "пять": 5, "пяти": 5,
    "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7,
    "восемь": 8, "восьми": 8,
    "девять": 9, "девяти": 9,
    "десять": 10, "десяти": 10,
    "одиннадцать": 11, "одиннадцати": 11,
    "двенадцать": 12, "двенадцати": 12,
    "тринадцать": 13, "тринадцати": 13,
    "четырнадцать": 14, "четырнадцати": 14,
    "пятнадцать": 15, "пятнадцати": 15,
    "шестнадцать": 16, "шестнадцати": 16,
    "семнадцать": 17, "семнадцати": 17,
    "восемнадцать": 18, "восемнадцати": 18,
    "девятнадцать": 19, "девятнадцати": 19,
}

_RU_TENS = {
    "двадцать": 20, "двадцати": 20,
    "тридцать": 30, "тридцати": 30,
    "сорок": 40, "сорока": 40,
    "пятьдесят": 50, "пятидесяти": 50,
    "шестьдесят": 60, "шестидесяти": 60,
    "семьдесят": 70, "семидесяти": 70,
    "восемьдесят": 80, "восьмидесяти": 80,
    "девяносто": 90, "девяноста": 90,
}

_EN_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_SUFFIX_WORDS = {"лет", "года", "год", "годик", "годиков", "годков", "years", "old", "y.o.", "yo"}


def parse_age(text: str) -> int | None:
    """
    Парсит возраст из произвольного текста.
    Понимает: "14", "14 лет", "четырнадцать", "двадцать три", "twenty three", "23 года".
    Возвращает int или None если не удалось распознать.
    """
    words = [w.strip(".,!?;:—-\"'") for w in text.lower().split()]
    words = [w for w in words if w and w not in _SUFFIX_WORDS]

    # Прямое число
    for w in words:
        try:
            age = int(w)
            if 1 <= age <= 100:
                return age
        except ValueError:
            pass

    # Словесная запись (суммируем десятки + единицы)
    total = 0
    found = False
    for w in words:
        if w in _RU_TENS:
            total += _RU_TENS[w]
            found = True
        elif w in _RU_UNITS:
            total += _RU_UNITS[w]
            found = True
        elif w in _EN_NUMBERS:
            total += _EN_NUMBERS[w]
            found = True

    if found and 1 <= total <= 100:
        return total

    return None


def extract_student_name(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    # "Анна Петрова (14)" / "Анна Петрова, 14" -> "Анна Петрова"
    raw = re.split(r"\(|,", raw, maxsplit=1)[0]
    return " ".join(raw.split()).strip()


# ─── Preferred-name derivation ─────────────────────────────────────────────────

_RU_SURNAME_SUFFIXES = (
    "ов", "ев", "ёв", "ин", "ын", "ский", "цкий", "ской",
    "ова", "ева", "ёва", "ина", "ына", "ская", "цкая",
)


def _looks_like_surname(token: str) -> bool:
    low = token.lower().replace("ё", "е")
    # Comparison: suffixes above include "ёв"/"ёва" forms; replacing ё→е
    # keeps the suffix list correct because "ев"/"ева" cover those cases.
    return any(low.endswith(suf.replace("ё", "е")) for suf in _RU_SURNAME_SUFFIXES)


def derive_preferred_name(full_name: str | None) -> str:
    """Heuristically extract a first name from a free-form full_name.

    Russian admin records often store "Last First" while UI registration tends
    to capture "First Last". This picks the token most likely to be a first
    name. The result is meant to be backfilled once into a `preferred_name`
    column and then editable in the admin UI.
    """
    if not full_name:
        return ""
    tokens = [t for t in full_name.strip().split() if t]
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    if len(tokens) == 2:
        a, b = tokens
        a_sur, b_sur = _looks_like_surname(a), _looks_like_surname(b)
        if a_sur and not b_sur:
            return b
        if b_sur and not a_sur:
            return a
        return a
    # 3+ tokens: official Russian order is Surname-First-Patronymic → token #2.
    return tokens[1]
