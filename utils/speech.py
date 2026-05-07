import logging
from functools import lru_cache

_logger = logging.getLogger(__name__)


FORMAL_SPEECH = "formal"
INFORMAL_SPEECH = "informal"
SCHOOLCHILD_SPEECH = "schoolchild"


def normalize_speech_style(value: str | None) -> str:
    if value == INFORMAL_SPEECH:
        return INFORMAL_SPEECH
    if value == SCHOOLCHILD_SPEECH:
        return SCHOOLCHILD_SPEECH
    return FORMAL_SPEECH


def is_formal_speech(value: str | None) -> bool:
    return normalize_speech_style(value) == FORMAL_SPEECH


def is_schoolchild_speech(value: str | None) -> bool:
    return normalize_speech_style(value) == SCHOOLCHILD_SPEECH


def speech_style_label(value: str | None) -> str:
    style = normalize_speech_style(value)
    if style == SCHOOLCHILD_SPEECH:
        return "школьник"
    if style == INFORMAL_SPEECH:
        return "на ты"
    return "на Вы"


def speech_style_toggle_label(value: str | None) -> str:
    style = normalize_speech_style(value)
    if style == SCHOOLCHILD_SPEECH:
        return "Переключить на Вы"
    if style == INFORMAL_SPEECH:
        return "Переключить на Вы"
    return "Переключить на ты"


def speech_style_icon(value: str | None) -> str:
    style = normalize_speech_style(value)
    if style == SCHOOLCHILD_SPEECH:
        return "🎒"
    return "🫱" if style == FORMAL_SPEECH else "🤝"


def choose_form(value: str | None, formal: str, informal: str, schoolchild: str | None = None) -> str:
    style = normalize_speech_style(value)
    if style == SCHOOLCHILD_SPEECH:
        return schoolchild if schoolchild is not None else informal
    if style == INFORMAL_SPEECH:
        return informal
    return formal


@lru_cache(maxsize=1)
def _petrovich_instance():
    try:
        from petrovich.main import Petrovich
        return Petrovich()
    except Exception as exc:
        _logger.warning("petrovich недоступен, имена не склоняются: %s", exc)
        return None


def _petrovich_gender_for_instrumental(first_name: str) -> str:
    """Pick petrovich gender flag that yields correct instrumental case.

    Petrovich correctly handles MALE flag for "Илья" (-> "Ильей"), but for other
    male names ending in -а/-я (Никита, Лука, Савва, Юра, Саша…) it returns the
    nominative when MALE is passed. For those, FEMALE flag produces the correct
    Russian instrumental form because nouns of the 2nd declension follow the
    same pattern regardless of grammatical gender (Никитой, Лукой, Сашей).
    """
    low = (first_name or "").lower().replace("ё", "е")
    if not low:
        return "male"
    if low == "илья":
        return "male"
    if low.endswith(("а", "я")):
        return "female"
    return "male"


def inflect_name_instrumental(name: str | None) -> str:
    """Return the given Russian first name in instrumental case ("с Полиной")."""
    if not name:
        return ""
    p = _petrovich_instance()
    if p is None:
        return name
    try:
        from petrovich.enums import Case, Gender
        gender_map = {"male": Gender.MALE, "female": Gender.FEMALE}
        first = name.split()[0]
        gender = gender_map[_petrovich_gender_for_instrumental(first)]
        return p.firstname(first, Case.INSTRUMENTAL, gender)
    except Exception as exc:
        _logger.warning("petrovich сломался на %r: %s", name, exc)
        return name
