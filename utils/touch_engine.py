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

    first_sentence_match = re.match(r"(.+?[.!?])\s", text)
    if first_sentence_match:
        result["raw_first_sentence"] = first_sentence_match.group(1).strip()
    else:
        result["raw_first_sentence"] = text[:100].strip()

    for pattern in _TOPIC_PATTERNS:
        m = pattern.search(text)
        if m:
            result["topic"] = m.group(1).strip()[:80]
            break

    for pattern in _DIFFICULTY_PATTERNS:
        m = pattern.search(text)
        if m:
            result["difficulty"] = m.group(1).strip()[:80]
            break

    for pattern in _TASK_PATTERNS:
        m = pattern.search(text)
        if m:
            result["task"] = m.group(1).strip()[:80]
            break

    if not result["topic"] and result["raw_first_sentence"]:
        result["topic"] = result["raw_first_sentence"]

    return result


# ── Touch type selection ─────────────────────────────────────────────────────

def select_touch_type(
    comment_data: dict,
    has_active_hw: bool,
    streak_weeks: int,
    balance: int,
    total_lessons: int = 0,
    goal_text: str | None = None,
    last_goal_reminder_days: int | None = None,
) -> str | None:
    """Decide which type of touch to send, or None if no touch should be sent.

    Priority:
    1. milestone_approaching (within 3 of [5, 10, 25, 50])
    2. support (difficulty from teacher comment)
    3. progress (topic from teacher comment)
    4. hw_nudge (active HW, no comment)
    5. goal_reminder (has goal, last reminder >14 days ago)
    6. motivation (streak >= 3)
    7. None
    """
    if balance <= 0:
        return None

    from utils.achievements import LESSON_MILESTONES
    for ms in LESSON_MILESTONES:
        remaining = ms - total_lessons
        if 1 <= remaining <= 3:
            return "milestone_approaching"

    if comment_data.get("topic") and comment_data.get("difficulty"):
        return "support"
    if comment_data.get("difficulty"):
        return "support"
    if comment_data.get("topic"):
        return "progress"
    if has_active_hw:
        return "hw_nudge"

    if goal_text and (last_goal_reminder_days is None or last_goal_reminder_days > 14):
        return "goal_reminder"

    if streak_weeks >= 3:
        return "motivation"
    return None


# ── Message rendering ────────────────────────────────────────────────────────

def _resolve_templates(
    templates: dict,
    tpl_key: str,
    tone: str,
    speech_style: str | None,
    is_pair: bool,
) -> list[str]:
    """Resolve template list, supporting both old and new format.

    Old format: type -> tone -> string or [strings]
    New format: type -> tone -> speech_style -> [strings]
    """
    type_templates = templates.get(tpl_key, {})
    if not type_templates and is_pair:
        base_key = tpl_key.replace("_pair", "")
        type_templates = templates.get(base_key, {})

    tone_data = type_templates.get(tone) or type_templates.get("warm", {})
    if not tone_data:
        return []

    if isinstance(tone_data, list):
        return tone_data
    if isinstance(tone_data, str):
        return [tone_data]

    if isinstance(tone_data, dict):
        ss = speech_style or "informal"
        variants = tone_data.get(ss) or tone_data.get("informal", [])
        if isinstance(variants, str):
            return [variants]
        return variants if isinstance(variants, list) else []

    return []


def render_touch_message(
    template_type: str,
    student_name: str,
    context: dict,
    brand_tone: str | None = None,
    speech_style: str | None = None,
    is_pair: bool = False,
    partner_name: str | None = None,
    last_template_index: int | None = None,
) -> tuple[str | None, int | None]:
    """Render a touch message from templates.

    Returns (message_text, template_index) or (None, None).
    """
    templates = _load_templates()
    if not templates:
        return None, None

    tpl_key = template_type
    if is_pair and partner_name:
        tpl_key = f"{template_type}_pair"

    tone = brand_tone or get_brand_tone()
    variants = _resolve_templates(templates, tpl_key, tone, speech_style, is_pair)

    if not variants:
        return None, None

    if len(variants) > 1 and last_template_index is not None:
        candidates = [i for i in range(len(variants)) if i != last_template_index]
        idx = random.choice(candidates) if candidates else 0
    else:
        idx = random.randrange(len(variants))

    template_str = variants[idx]

    from utils.speech import inflect_name_instrumental

    topic = context.get("topic") or context.get("difficulty") or context.get("raw_first_sentence") or ""
    inflected_partner = inflect_name_instrumental(partner_name) if partner_name else ""
    message = template_str.replace("{name}", student_name)
    message = message.replace("{topic}", topic)
    message = message.replace("{partner}", inflected_partner)
    message = message.replace("{N}", str(context.get("N", 0)))
    message = message.replace("{streak}", str(context.get("N", 0)))
    message = message.replace("{total_lessons}", str(context.get("total_lessons", 0)))
    message = message.replace("{goal}", str(context.get("goal", "")))
    message = message.replace("{next_milestone_text}", str(context.get("next_milestone_text", "")))

    return message.strip(), idx


# ── Send decision ────────────────────────────────────────────────────────────

TOUCHES_WEEKLY_CAP = 1
TOUCHES_TEMPLATE_TYPE_COOLDOWN_DAYS = 7


def should_send_touch(
    last_lesson: datetime | None,
    next_lesson: datetime | None,
    recent_touches: list,
    today: date,
    balance: int,
    candidate_template_type: str | None = None,
) -> bool:
    """Decide whether a touch should be sent today.

    Args:
        recent_touches: rows from `get_recent_touches` over the past 7 days,
            ordered DESC by `sent_at`. Each row carries `sent_at` and
            `template_type` (and `template_index` after the dedup fix).
        candidate_template_type: when known, also enforces a per-template-type
            cooldown so we never repeat the same kind of message inside the
            cooldown window.
    """
    if balance <= 0:
        return False
    if last_lesson is None:
        return False
    if last_lesson.date() == today:
        return False
    if next_lesson and next_lesson.date() == today:
        return False

    # At most one touch per student per day, regardless of type.
    for t in (recent_touches or []):
        sent_at = t.get("sent_at") if isinstance(t, dict) else None
        if sent_at is not None and sent_at.date() == today:
            return False

    # Weekly cap.
    if len(recent_touches or []) >= TOUCHES_WEEKLY_CAP:
        return False

    # Per-template-type cooldown.
    if candidate_template_type is not None:
        cutoff = datetime.combine(today, datetime.min.time()) - timedelta(
            days=TOUCHES_TEMPLATE_TYPE_COOLDOWN_DAYS
        )
        for t in (recent_touches or []):
            if not isinstance(t, dict):
                continue
            if t.get("template_type") != candidate_template_type:
                continue
            sent_at = t.get("sent_at")
            if sent_at is not None and sent_at >= cutoff:
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
