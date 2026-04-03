from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND_SETTINGS_FILE = PROJECT_ROOT / "data" / "brand_settings.json"

STRICT_TONE = "strict"
NEUTRAL_TONE = "neutral"
WARM_TONE = "warm"
PREMIUM_TONE = "premium"
DEFAULT_BRAND_TONE = WARM_TONE

BRAND_TONE_LABELS = {
    STRICT_TONE: "строгий",
    NEUTRAL_TONE: "нейтральный",
    WARM_TONE: "тёплый",
    PREMIUM_TONE: "премиальный",
}

BRAND_TONE_DESCRIPTIONS = {
    STRICT_TONE: "Прямые и сухие формулировки, минимум смягчения.",
    NEUTRAL_TONE: "Спокойные рабочие формулировки без лишней эмоциональности.",
    WARM_TONE: "Дружелюбные и мягкие формулировки, близкие к текущему стилю бота.",
    PREMIUM_TONE: "Сдержанные, аккуратные и более салонные формулировки.",
}


def normalize_brand_tone(value: str | None) -> str:
    return value if value in BRAND_TONE_LABELS else DEFAULT_BRAND_TONE


def brand_tone_label(value: str | None) -> str:
    return BRAND_TONE_LABELS[normalize_brand_tone(value)]


def brand_tone_description(value: str | None) -> str:
    return BRAND_TONE_DESCRIPTIONS[normalize_brand_tone(value)]


def load_brand_settings() -> dict:
    if not BRAND_SETTINGS_FILE.exists():
        return {"tone": DEFAULT_BRAND_TONE}
    try:
        payload = json.loads(BRAND_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tone": DEFAULT_BRAND_TONE}
    payload["tone"] = normalize_brand_tone(payload.get("tone"))
    return payload


def get_brand_tone() -> str:
    return normalize_brand_tone(load_brand_settings().get("tone"))


def set_brand_tone(value: str | None) -> str:
    tone = normalize_brand_tone(value)
    BRAND_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRAND_SETTINGS_FILE.write_text(
        json.dumps({"tone": tone}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tone


def choose_tone_variant(
    strict: str,
    neutral: str,
    warm: str,
    premium: str,
    tone: str | None = None,
) -> str:
    current = normalize_brand_tone(tone or get_brand_tone())
    variants = {
        STRICT_TONE: strict,
        NEUTRAL_TONE: neutral,
        WARM_TONE: warm,
        PREMIUM_TONE: premium,
    }
    return variants[current]
