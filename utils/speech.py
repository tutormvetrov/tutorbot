FORMAL_SPEECH = "formal"
INFORMAL_SPEECH = "informal"


def normalize_speech_style(value: str | None) -> str:
    return INFORMAL_SPEECH if value == INFORMAL_SPEECH else FORMAL_SPEECH


def is_formal_speech(value: str | None) -> bool:
    return normalize_speech_style(value) == FORMAL_SPEECH


def speech_style_label(value: str | None) -> str:
    return "на Вы" if is_formal_speech(value) else "на ты"


def speech_style_toggle_label(value: str | None) -> str:
    return "Переключить на ты" if is_formal_speech(value) else "Переключить на Вы"


def speech_style_icon(value: str | None) -> str:
    return "🫱" if is_formal_speech(value) else "🤝"


def choose_form(value: str | None, formal: str, informal: str) -> str:
    return formal if is_formal_speech(value) else informal
