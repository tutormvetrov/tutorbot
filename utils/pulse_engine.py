"""Teacher Pulse: shared computation engine for health dashboard, briefing, nudges."""
from __future__ import annotations

from datetime import date, datetime, timedelta, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from data.config import BUSINESS_TIMEZONE
from utils.time import business_today

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database


# ── Traffic light thresholds ─────────────────────────────────────────────────

_RED_BALANCE = 0
_YELLOW_BALANCE = 1
_RED_NO_HW_HOURS = 24
_YELLOW_NO_HW_HOURS = 6
_RED_NO_LESSON_DAYS = 14
_YELLOW_NO_LESSON_DAYS = 7
_PAYMENT_GRACE_HOURS = 48  # урок прошёл недавно — оплата могла не залогироваться


# ── Quiet hours ──────────────────────────────────────────────────────────────

QUIET_START_HOUR = 22
QUIET_END_HOUR = 8
ADMIN_QUIET_END_HOUR = 8
STUDENT_QUIET_END_HOUR = 9


def is_quiet_hours(dt: datetime, *, for_student: bool = False) -> bool:
    """Check if the given datetime falls within quiet hours (22:00-08:00/09:00 MSK)."""
    tz = BUSINESS_TIMEZONE
    local = dt.astimezone(tz) if dt.tzinfo else dt
    hour = local.hour
    end = STUDENT_QUIET_END_HOUR if for_student else ADMIN_QUIET_END_HOUR
    if QUIET_START_HOUR > end:
        return hour >= QUIET_START_HOUR or hour < end
    return QUIET_START_HOUR <= hour < end


def next_active_time(dt: datetime, *, for_student: bool = False) -> datetime:
    """If dt is in quiet hours, return the next active-hours start; otherwise return dt."""
    if not is_quiet_hours(dt, for_student=for_student):
        return dt
    tz = BUSINESS_TIMEZONE
    local = dt.astimezone(tz) if dt.tzinfo else dt
    end = STUDENT_QUIET_END_HOUR if for_student else ADMIN_QUIET_END_HOUR
    next_day = local.date()
    if local.hour >= QUIET_START_HOUR:
        next_day += timedelta(days=1)
    return datetime.combine(next_day, time(end, 0), tzinfo=tz)


# ── Student health computation ───────────────────────────────────────────────

def compute_student_health(row: dict, now: datetime | None = None) -> dict:
    """Compute a single student's traffic-light health from a pulse data row.

    Args:
        row: a dict from DatabasePulseMixin.get_all_pulse_data()
        now: override for testing; defaults to current time.

    Returns:
        dict with keys: color, reasons, days_since_last_lesson,
        days_since_last_hw, balance, open_nudges, streak_weeks,
        full_name, telegram_id, is_pair, pair_title.
    """
    if now is None:
        now = datetime.now()

    balance = int(row.get("balance") or 0)
    open_nudges = int(row.get("open_nudge_count") or 0)

    last_lesson_date = row.get("last_lesson_date")
    last_hw_date = row.get("last_hw_created_at")
    first_lesson_date = row.get("first_lesson_date")
    total_lessons = int(row.get("total_lessons") or 0)

    days_since_last_lesson: int | None = None
    if last_lesson_date:
        delta = now - last_lesson_date
        days_since_last_lesson = max(0, delta.days)

    days_since_last_hw: int | None = None
    if last_hw_date:
        delta = now - last_hw_date
        days_since_last_hw = max(0, delta.days)

    # Hours since last lesson (for HW nudge threshold)
    hours_since_last_lesson: float | None = None
    if last_lesson_date:
        hours_since_last_lesson = max(0.0, (now - last_lesson_date).total_seconds() / 3600)

    # Streak: consecutive weeks with at least one lesson
    streak_weeks = _compute_streak_weeks(first_lesson_date, last_lesson_date, total_lessons, now)

    # ── Determine color ──
    reasons: list[str] = []

    # Red conditions
    if balance <= _RED_BALANCE:
        hours_since_lesson = (
            (now - last_lesson_date).total_seconds() / 3600
            if last_lesson_date else None
        )
        if hours_since_lesson is not None and hours_since_lesson <= _PAYMENT_GRACE_HOURS:
            reasons.append("payment_not_logged")
        else:
            reasons.append("balance_0")
    if hours_since_last_lesson is not None and hours_since_last_lesson > _RED_NO_HW_HOURS:
        if last_hw_date is None or (last_lesson_date and last_hw_date < last_lesson_date):
            reasons.append("no_hw_24h")
    if days_since_last_lesson is not None and days_since_last_lesson > _RED_NO_LESSON_DAYS:
        reasons.append("no_lesson_14d")

    red_reasons = {"balance_0", "no_hw_24h", "no_lesson_14d"}
    is_red = bool(reasons and (set(reasons) & red_reasons))

    # Yellow conditions (only if not already red for that metric)
    if not is_red:
        if balance == _YELLOW_BALANCE:
            reasons.append("balance_1")
        if hours_since_last_lesson is not None and hours_since_last_lesson > _YELLOW_NO_HW_HOURS:
            if last_hw_date is None or (last_lesson_date and last_hw_date < last_lesson_date):
                reasons.append("no_hw_6h")
        if (
            days_since_last_lesson is not None
            and _YELLOW_NO_LESSON_DAYS <= days_since_last_lesson <= _RED_NO_LESSON_DAYS
        ):
            reasons.append("no_lesson_7d")

    yellow_reasons = {"balance_1", "no_hw_6h", "no_lesson_7d", "payment_not_logged"}

    if is_red:
        color = "red"
    elif set(reasons) & yellow_reasons:
        color = "yellow"
    else:
        color = "green"

    return {
        "color": color,
        "reasons": reasons,
        "days_since_last_lesson": days_since_last_lesson,
        "days_since_last_hw": days_since_last_hw,
        "balance": balance,
        "open_nudges": open_nudges,
        "streak_weeks": streak_weeks,
        "full_name": row.get("full_name") or "---",
        "telegram_id": row.get("telegram_id"),
        "is_pair": bool(row.get("is_pair")),
        "pair_title": row.get("pair_title"),
    }


def _compute_streak_weeks(
    first_lesson: datetime | None,
    last_lesson: datetime | None,
    total_lessons: int,
    now: datetime,
) -> int:
    """Approximate streak in weeks.

    Simple heuristic: if the student had a lesson within the last 10 days,
    the streak is the number of weeks between first lesson and now.
    Otherwise streak is 0.
    """
    if not first_lesson or not last_lesson or total_lessons == 0:
        return 0
    if (now - last_lesson).days > 10:
        return 0
    return max(1, (now - first_lesson).days // 7)


# ── Aggregate health for all students ────────────────────────────────────────

COLOR_ORDER = {"red": 0, "yellow": 1, "green": 2}


async def compute_all_health(db: "Database", now: datetime | None = None) -> list[dict]:
    """Compute health for all active students, sorted red-first."""
    rows = await db.get_all_pulse_data()
    if now is None:
        now = datetime.now()

    health_list = [compute_student_health(row, now=now) for row in (rows or [])]
    health_list.sort(key=lambda h: (COLOR_ORDER.get(h["color"], 9), h["full_name"]))
    return health_list


# ── Text formatting ──────────────────────────────────────────────────────────

_COLOR_EMOJI = {"red": "\U0001f534", "yellow": "\U0001f7e1", "green": "\U0001f7e2"}


def _reason_label(reason: str) -> str:
    labels = {
        "balance_0": "баланс 0",
        "balance_1": "баланс 1 урок",
        "no_hw_24h": "ДЗ не отправлено >24ч",
        "no_hw_6h": "ДЗ не отправлено >6ч",
        "no_lesson_14d": "нет уроков >14 дней",
        "no_lesson_7d": "нет уроков 7-14 дней",
        "payment_not_logged": "внеси оплату",
    }
    return labels.get(reason, reason)


def _student_display_name(health: dict) -> str:
    if health.get("is_pair") and health.get("pair_title"):
        return health["pair_title"]
    return health["full_name"]


def build_pulse_text(health_list: list[dict], today_date: date | None = None) -> str:
    """Format the Pulse screen text."""
    if today_date is None:
        today_date = business_today()

    weekday_names = {
        0: "понедельник",
        1: "вторник",
        2: "среда",
        3: "четверг",
        4: "пятница",
        5: "суббота",
        6: "воскресенье",
    }
    month_names = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }

    day_label = f"{today_date.day} {month_names.get(today_date.month, '')}"
    weekday_label = weekday_names.get(today_date.weekday(), "")
    header = f"\U0001f4ca <b>Пульс</b> - {day_label}, {weekday_label}\n"

    if not health_list:
        return header + "\nНет активных учеников."

    lines: list[str] = [header]
    for h in health_list:
        emoji = _COLOR_EMOJI.get(h["color"], "⬜")
        name = _student_display_name(h)
        if h["color"] == "green":
            streak = h.get("streak_weeks", 0)
            suffix = f"streak {streak} нед." if streak >= 3 else ""
            detail = f"всё ок{' (' + suffix + ')' if suffix else ''}"
        else:
            detail = ", ".join(_reason_label(r) for r in h["reasons"]) if h["reasons"] else "..."
        lines.append(f"{emoji} {name} - {detail}")

    counts = {"red": 0, "yellow": 0, "green": 0}
    for h in health_list:
        counts[h["color"]] = counts.get(h["color"], 0) + 1

    lines.append("")
    lines.append(
        f"\U0001f534 {counts['red']}  \U0001f7e1 {counts['yellow']}  \U0001f7e2 {counts['green']}"
    )

    return "\n".join(lines)


def build_briefing_text(
    health_list: list[dict],
    today_lessons: list[dict],
    today_date: date | None = None,
) -> str:
    """Format the morning briefing message."""
    if today_date is None:
        today_date = business_today()

    weekday_names = {
        0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
        4: "пятница", 5: "суббота", 6: "воскресенье",
    }
    month_names = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }

    day_label = f"{today_date.day} {month_names.get(today_date.month, '')}"
    weekday_label = weekday_names.get(today_date.weekday(), "")

    lines: list[str] = [
        f"☀️ Доброе утро! Сводка на {day_label}, {weekday_label}\n"
    ]

    # Lessons block
    if today_lessons:
        lines.append(f"\U0001f4c5 <b>Уроки сегодня: {len(today_lessons)}</b>")
        for lesson in today_lessons:
            ld = lesson.get("lesson_date")
            time_str = ld.strftime("%H:%M") if ld else "---"
            name = lesson.get("full_name") or "---"
            if lesson.get("is_pair") and lesson.get("pair_title"):
                name = lesson["pair_title"]
            lines.append(f"   {time_str} - {name}")
        lines.append("")

    # Problems block
    problems = [h for h in health_list if h["color"] in ("red", "yellow")]
    if problems:
        lines.append("⚠️ <b>Требует внимания:</b>")
        for h in problems:
            emoji = _COLOR_EMOJI.get(h["color"], "")
            name = _student_display_name(h)
            detail = ", ".join(_reason_label(r) for r in h["reasons"]) if h["reasons"] else "..."
            lines.append(f"   {emoji} {name} - {detail}")
        lines.append("")

    ok_count = sum(1 for h in health_list if h["color"] == "green")
    if ok_count > 0:
        lines.append(f"✅ Остальные {ok_count} учеников - всё в порядке.")

    return "\n".join(lines)


def should_send_briefing(health_list: list[dict], today_lessons: list[dict]) -> bool:
    """Decide whether the morning briefing should be sent.

    Skip if there are no lessons today AND no problems.
    """
    has_lessons = bool(today_lessons)
    has_problems = any(h["color"] in ("red", "yellow") for h in health_list)
    return has_lessons or has_problems


def get_most_urgent_student_id(health_list: list[dict]) -> int | None:
    """Return the telegram_id of the most urgent red student (for quick-action button)."""
    for h in health_list:
        if h["color"] == "red" and h.get("telegram_id"):
            return h["telegram_id"]
    return None
