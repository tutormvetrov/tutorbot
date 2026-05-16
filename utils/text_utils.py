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


# Pair-name parsing


def _clean_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _split_pair_parts(value: str) -> list[str]:
    raw = _clean_name(value)
    if not raw:
        return []
    if "+" in raw:
        return [_clean_name(part) for part in raw.split("+") if _clean_name(part)]
    parts = re.split(r"\s+и\s+", raw, maxsplit=1, flags=re.IGNORECASE)
    return [_clean_name(part) for part in parts if _clean_name(part)]


def _singular_surname(value: str | None) -> str:
    token = _clean_name(value)
    if not token:
        return ""
    low = token.lower().replace("ё", "е")
    if low.endswith("ские"):
        return token[:-2] + "й"
    if low.endswith("цкие"):
        return token[:-2] + "й"
    if low.endswith("овы") or low.endswith("евы") or low.endswith("ёвы") or low.endswith("ины"):
        return token[:-1]
    if low.endswith("ые") or low.endswith("ие"):
        return token[:-2]
    if low.endswith("ова") or low.endswith("ева") or low.endswith("ёва") or low.endswith("ина"):
        return token[:-1]
    if low.endswith("ая"):
        return token[:-2] + "ий"
    return token


def family_surname_label(surname: str | None) -> str:
    base = _singular_surname(surname)
    if not base:
        return ""
    low = base.lower().replace("ё", "е")
    if low.endswith("ский") or low.endswith("цкий"):
        return base[:-2] + "ие"
    if low.endswith("ой"):
        return base[:-2] + "ые"
    if low.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return base + "ы"
    return base


def parse_person_name(value: str | None, *, default_surname: str | None = None) -> dict:
    raw = _clean_name(value)
    tokens = raw.split()
    if not tokens:
        return {"raw": "", "given": "", "surname": _clean_name(default_surname), "display": ""}
    if len(tokens) == 1:
        surname = _clean_name(default_surname)
        return {"raw": raw, "given": tokens[0], "surname": surname, "display": raw}

    first, second = tokens[0], tokens[1]
    first_is_surname = _looks_like_surname(first)
    second_is_surname = _looks_like_surname(second)
    if first_is_surname and not second_is_surname:
        surname = _singular_surname(first)
        display_surname = first
        given = second
    elif second_is_surname and not first_is_surname:
        surname = _singular_surname(second)
        display_surname = second
        given = first
    elif second_is_surname:
        surname = _singular_surname(second)
        display_surname = second
        given = first
    else:
        surname = _singular_surname(first)
        display_surname = first
        given = second

    rest = tokens[2:]
    display = f"{given} {display_surname}".strip()
    if rest:
        display = f"{display} {' '.join(rest)}"
    return {"raw": raw, "given": given, "surname": surname, "display": display}


def build_pair_display_title(
    primary_name: str,
    partner_name: str,
    *,
    common_surname: str | None = None,
) -> str:
    primary = parse_person_name(primary_name)
    surname = _singular_surname(common_surname)
    partner = parse_person_name(partner_name, default_surname=surname or primary.get("surname"))
    primary_given = primary.get("given") or _clean_name(primary_name)
    partner_given = partner.get("given") or _clean_name(partner_name)

    if surname:
        family = family_surname_label(surname)
        if family and primary_given and partner_given:
            return f"{family} {primary_given} и {partner_given}"

    p_surname = primary.get("surname") or ""
    s_surname = partner.get("surname") or ""
    if p_surname and s_surname and normalize_pair_token(p_surname) == normalize_pair_token(s_surname):
        family = family_surname_label(p_surname)
        if family and primary_given and partner_given:
            return f"{family} {primary_given} и {partner_given}"

    left = primary.get("display") or _clean_name(primary_name)
    right = partner.get("display") or _clean_name(partner_name)
    if left and right:
        return f"{left} и {right}"
    return left or right


def normalize_pair_token(value: str | None) -> str:
    return _singular_surname(value).lower().replace("ё", "е")


def parse_pair_name_input(primary_name: str, partner_input: str) -> dict:
    primary_clean = _clean_name(primary_name)
    partner_clean = _clean_name(partner_input)
    parts = _split_pair_parts(partner_clean)

    common_surname = ""
    primary_result = primary_clean
    partner_result = partner_clean

    if len(parts) >= 2:
        first_tokens = parts[0].split()
        if len(first_tokens) == 1 and not _looks_like_surname(first_tokens[0]):
            primary_result = parts[0]
            partner_result = parts[1]
        elif len(first_tokens) >= 3 and not _looks_like_surname(first_tokens[0]):
            common_surname = _singular_surname(first_tokens[0])
            primary_result = first_tokens[1]
            partner_result = parts[1]
        else:
            primary_result = parts[0]
            partner_result = parts[1]
            primary_person = parse_person_name(primary_result)
            partner_person = parse_person_name(partner_result)
            if primary_person.get("surname") and not partner_person.get("surname"):
                common_surname = primary_person["surname"]
    else:
        primary_person = parse_person_name(primary_clean)
        partner_person = parse_person_name(partner_clean, default_surname=primary_person.get("surname"))
        if primary_person.get("surname") and not parse_person_name(partner_clean).get("surname"):
            common_surname = primary_person["surname"]
        primary_result = primary_clean
        partner_result = partner_person.get("raw") or partner_clean

    if common_surname:
        partner_result = parse_person_name(partner_result, default_surname=common_surname).get("given") or partner_result

    title = build_pair_display_title(primary_result, partner_result, common_surname=common_surname)
    return {
        "primary_name": primary_result,
        "partner_name": partner_result,
        "common_surname": common_surname or None,
        "title": title,
    }
