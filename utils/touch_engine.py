"""Between-Lesson Touch Engine: parsing teacher notes, selecting and rendering touches."""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from utils.brand import get_brand_tone
from utils.speech import choose_form

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "data" / "touch_templates.json"
_templates_cache: dict | None = None


def _load_templates() -> dict:
    """Load touch templates, cached after first read."""
    global _templates_cache
    if _templates_cache is not None:
        return _templates_cache
    try:
        _templates_cache = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Не удалось загрузить touch_templates.json: %s", exc)
        _templates_cache = {}
    return _templates_cache


def reload_templates() -> None:
    """Force reload templates (useful for testing)."""
    global _templates_cache
    _templates_cache = None


# ── Teacher comment parsing ──────────────────────────────────────────────────

_TOPIC_PATTERNS = [
    re.compile(r"(?:разобрали|прошли|работали над|тема:?)\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
    re.compile(r"(?:тема)\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
]

_DIFFICULTY_PATTERNS = [
    re.compile(r"(?:сложно далось?|трудно|проблема с|ошибки в)\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
    re.compile(r"(?:не получается|путает|путаница с)\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
]

_TASK_PATTERNS = [
    re.compile(r"(?:задание:?|задано|повторить|д/?з:?)\s+(.+?)(?:\.|,|$)", re.IGNORECASE),
]


def parse_teacher_comment(comment: str | None) -> dict:
    """Extract structured info from a free-form teacher comment.

    Returns dict with keys: topic, difficulty, task, raw_first_sentence.
    Each value is str | None.
    """
    result = {"topic": None, "difficulty": None, "task": None, "raw_first_sentence": None}

    if not comment or len(comment.strip()) < 10:
        return result

    text = comment.strip()

    # Extract first sentence
    first_sentence_match = re.match(r"(.+?[.!?])\s", text)
    if first_sentence_match:
        result["raw_first_sentence"] = first_sentence_match.group(1).strip()
    else:
        result["raw_first_sentence"] = text[:100].strip()

    # Try topic patterns
    for pattern in _TOPIC_PATTERNS:
        m = pattern.search(text)
        if m:
            result["topic"] = m.group(1).strip()[:80]
            break

    # Try difficulty patterns
    for pattern in _DIFFICULTY_PATTERNS:
        m = pattern.search(text)
        if m:
            result["difficulty"] = m.group(1).strip()[:80]
            break

    # Try task patterns
    for pattern in _TASK_PATTERNS:
        m = pattern.search(text)
        if m:
            result["task"] = m.group(1).strip()[:80]
            break

    # If no topic found, use first sentence as topic
    if not result["topic"] and result["raw_first_sentence"]:
        result["topic"] = result["raw_first_sentence"]

    return result


# ── Touch type selection ─────────────────────────────────────────────────────

def select_touch_type(
    comment_data: dict,
    has_active_hw: bool,
    streak_weeks: int,
    balance: int,
    homework_exempt: bool = False,
) -> str | None:
    """Decide which type of touch to send, or None if no touch should be sent.

    Decision tree:
    1. Has topic from teacher_comment -> "progress"
    2. Has difficulty from teacher_comment -> "support"
    3. No comment data but active HW -> "hw_nudge" (skipped if homework_exempt)
    4. streak >= 3 weeks -> "motivation"
    5. Otherwise -> None (don't send)

    Also: balance <= 0 -> None (don't motivate unpaid student)
    """
    if balance <= 0:
        return None

    if comment_data.get("topic") and comment_data.get("difficulty"):
        # If both topic and difficulty, prefer support (more personal)
        return "support"
    if comment_data.get("difficulty"):
        return "support"
    if comment_data.get("topic"):
        return "progress"
    if has_active_hw and not homework_exempt:
        return "hw_nudge"
    if streak_weeks >= 3:
        return "motivation"
    return None


# ── Message rendering ────────────────────────────────────────────────────────

def render_touch_message(
    template_type: str,
    student_name: str,
    context: dict,
    brand_tone: str | None = None,
    speech_style: str | None = None,
    is_pair: bool = False,
    partner_name: str | None = None,
) -> str | None:
    """Render a touch message from templates.

    Args:
        template_type: "progress", "support", "hw_nudge", "motivation"
        student_name: student's first name or full name
        context: dict with "topic", "difficulty", "N" (streak), etc.
        brand_tone: "warm", "premium", "neutral", "strict"
        speech_style: "formal" or None (informal)
        is_pair: whether this is a pair student
        partner_name: partner's name for pair touches

    Returns rendered message text, or None if template not found.
    """
    templates = _load_templates()
    if not templates:
        return None

    # Determine template key
    tpl_key = template_type
    if is_pair and partner_name:
        tpl_key = f"{template_type}_pair"

    tone = brand_tone or get_brand_tone()
    type_templates = templates.get(tpl_key, {})
    if not type_templates:
        # Fallback to non-pair version
        type_templates = templates.get(template_type, {})

    tone_variants = type_templates.get(tone)
    if not tone_variants:
        # Fallback to "warm"
        tone_variants = type_templates.get("warm", [])
    if not tone_variants:
        return None

    # Pick random variant
    template_str = random.choice(tone_variants)

    # Substitute placeholders
    topic = context.get("topic") or context.get("difficulty") or context.get("raw_first_sentence") or ""
    message = template_str.replace("{name}", student_name)
    message = message.replace("{topic}", topic)
    message = message.replace("{partner}", partner_name or "")
    message = message.replace("{N}", str(context.get("N", 0)))

    # Apply speech style (formal = Вы, informal = ты)
    if speech_style == "formal":
        # Templates are written in informal by default; for formal, apply choose_form
        # This is a simplified approach - templates should ideally have both forms
        message = message.replace("попробуй", "попробуйте")
        message = message.replace("не стесняйся", "не стесняйтесь")
        message = message.replace("не переживай", "не переживайте")
        message = message.replace("пиши", "пишите")
        message = message.replace("обрати", "обратите")
        message = message.replace("продолжай", "продолжайте")
        message = message.replace("задавай", "задавайте")
        message = message.replace("так держать", "продолжайте в том же духе")
        message = message.replace("молодец", "")
        message = message.replace("застрял", "застряли")
        message = message.replace("проверь", "проверьте")

    return message.strip()


# ── Send decision ────────────────────────────────────────────────────────────

def should_send_touch(
    last_lesson: datetime | None,
    next_lesson: datetime | None,
    touches_this_week: int,
    today: date,
    balance: int,
) -> bool:
    """Decide whether a touch should be sent today.

    Rules:
    - Max 2 per week
    - Not on lesson day
    - Balance > 0
    - Must have last_lesson (otherwise nothing to reference)
    """
    if touches_this_week >= 2:
        return False
    if balance <= 0:
        return False
    if last_lesson is None:
        return False

    # Not on lesson day
    if last_lesson.date() == today:
        return False
    if next_lesson and next_lesson.date() == today:
        return False

    return True


def compute_touch_send_time(last_lesson: datetime, next_lesson: datetime) -> datetime:
    """Compute the optimal send time: midpoint + random shift 2-4h."""
    midpoint = last_lesson + (next_lesson - last_lesson) / 2
    shift_hours = random.uniform(2.0, 4.0)
    return midpoint + timedelta(hours=shift_hours)


def is_in_send_window(send_time: datetime, now: datetime, window_hours: float = 1.0) -> bool:
    """Check if now is within the send window around the computed send_time."""
    delta = abs((now - send_time).total_seconds()) / 3600
    return delta <= window_hours
