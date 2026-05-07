"""Achievement definitions and engine for student milestones."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from utils.speech import choose_form

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database

ACHIEVEMENTS = [
    {
        "key": "first_lesson",
        "icon": "\U0001f393",
        "name": "Первый шаг",
        "check": lambda m: m["total_lessons"] >= 1,
        "remaining": lambda m: max(0, 1 - m["total_lessons"]),
        "remaining_label": "проведи первый урок",
    },
    {
        "key": "lessons_5",
        "icon": "⭐",
        "name": "Пятёрка",
        "check": lambda m: m["total_lessons"] >= 5,
        "remaining": lambda m: max(0, 5 - m["total_lessons"]),
        "remaining_label": lambda m: f"ещё {max(0, 5 - m['total_lessons'])} ур.",
    },
    {
        "key": "lessons_10",
        "icon": "\U0001f51f",
        "name": "Десятка",
        "check": lambda m: m["total_lessons"] >= 10,
        "remaining": lambda m: max(0, 10 - m["total_lessons"]),
        "remaining_label": lambda m: f"ещё {max(0, 10 - m['total_lessons'])} ур.",
    },
    {
        "key": "lessons_25",
        "icon": "\U0001f3c5",
        "name": "Четверть",
        "check": lambda m: m["total_lessons"] >= 25,
        "remaining": lambda m: max(0, 25 - m["total_lessons"]),
        "remaining_label": lambda m: f"ещё {max(0, 25 - m['total_lessons'])} ур.",
    },
    {
        "key": "lessons_50",
        "icon": "\U0001f3c6",
        "name": "Полтинник",
        "check": lambda m: m["total_lessons"] >= 50,
        "remaining": lambda m: max(0, 50 - m["total_lessons"]),
        "remaining_label": lambda m: f"ещё {max(0, 50 - m['total_lessons'])} ур.",
    },
    {
        "key": "streak_4",
        "icon": "\U0001f525",
        "name": "Марафонец",
        "check": lambda m: m["streak_weeks"] >= 4,
        "remaining": lambda m: max(0, 4 - m["streak_weeks"]),
        "remaining_label": lambda m: f"ещё {max(0, 4 - m['streak_weeks'])} нед.",
    },
    {
        "key": "streak_12",
        "icon": "\U0001f48e",
        "name": "Стальная привычка",
        "check": lambda m: m["streak_weeks"] >= 12,
        "remaining": lambda m: max(0, 12 - m["streak_weeks"]),
        "remaining_label": lambda m: f"ещё {max(0, 12 - m['streak_weeks'])} нед.",
    },
    {
        "key": "hw_perfect_month",
        "icon": "\U0001f4da",
        "name": "Отличник",
        "check": lambda m: m.get("hw_perfect_months", 0) > 0,
        "remaining": lambda _m: 0,
        "remaining_label": "сдай все ДЗ в срок за месяц",
    },
    {
        "key": "plan_complete",
        "icon": "\U0001f4cc",
        "name": "Планомер",
        "check": lambda m: m.get("plan_total", 0) > 0 and m.get("plan_done", 0) == m.get("plan_total", 0),
        "remaining": lambda _m: 0,
        "remaining_label": "заверши учебный план",
    },
    {
        "key": "tenure_26w",
        "icon": "\U0001f382",
        "name": "Полгода вместе",
        "check": lambda m: m.get("tenure_weeks", 0) >= 26,
        "remaining": lambda m: max(0, 26 - m.get("tenure_weeks", 0)),
        "remaining_label": lambda m: f"через {max(0, 26 - m.get('tenure_weeks', 0))} нед.",
    },
    {
        "key": "tenure_52w",
        "icon": "\U0001f38a",
        "name": "Год вместе",
        "check": lambda m: m.get("tenure_weeks", 0) >= 52,
        "remaining": lambda m: max(0, 52 - m.get("tenure_weeks", 0)),
        "remaining_label": lambda m: f"через {max(0, 52 - m.get('tenure_weeks', 0))} нед.",
    },
    {
        "key": "goal_set",
        "icon": "\U0001f3af",
        "name": "Целеустремлённый",
        "check": lambda m: bool(m.get("goal_text")),
        "remaining": lambda _m: 0,
        "remaining_label": "поставь цель",
    },
]

ACHIEVEMENT_COUNT = len(ACHIEVEMENTS)
ACHIEVEMENT_BY_KEY = {a["key"]: a for a in ACHIEVEMENTS}

LESSON_MILESTONES = [5, 10, 25, 50]


def _congrats_text(key: str, speech_style: str | None = None) -> str:
    """Short congratulation text per achievement, adapted to speech style."""
    ss = speech_style or "informal"
    texts = {
        "first_lesson": {
            "informal": "Первый урок позади. Хорошее начало!",
            "formal": "Первый урок позади. Отличное начало!",
            "schoolchild": "Первый урок позади. Ура!",
        },
        "lessons_5": {
            "informal": "5 уроков — ты втянулся!",
            "formal": "5 уроков — отличный темп!",
            "schoolchild": "5 уроков — круто!",
        },
        "lessons_10": {
            "informal": "10 уроков — двузначная цифра, серьёзно!",
            "formal": "10 уроков — достойный результат!",
            "schoolchild": "10 уроков! Двузначное число!",
        },
        "lessons_25": {
            "informal": "Четверть сотни уроков. Настоящий прогресс!",
            "formal": "25 уроков — значительный путь пройден!",
            "schoolchild": "25 уроков! Четвертак!",
        },
        "lessons_50": {
            "informal": "Полтинник! 50 уроков — это нешуточный результат.",
            "formal": "50 уроков — впечатляющая дисциплина!",
            "schoolchild": "50 уроков! Полсотни! Ты монстр!",
        },
        "streak_4": {
            "informal": "4 недели подряд без пропусков. Привычка формируется!",
            "formal": "4 недели регулярных занятий. Прекрасная стабильность!",
            "schoolchild": "4 недели подряд! Не сбиваешься!",
        },
        "streak_12": {
            "informal": "12 недель подряд — стальная привычка. Респект!",
            "formal": "12 недель регулярных занятий — выдающаяся дисциплина!",
            "schoolchild": "12 недель подряд! Ты железный!",
        },
        "hw_perfect_month": {
            "informal": "Все ДЗ за месяц сданы в срок. Образцовый ученик!",
            "formal": "Все задания за месяц выполнены в срок. Превосходно!",
            "schoolchild": "Все домашки за месяц сделаны вовремя! Красавчик!",
        },
        "plan_complete": {
            "informal": "Учебный план выполнен на 100%. Ты прошёл весь путь!",
            "formal": "Учебный план полностью завершён. Великолепно!",
            "schoolchild": "Весь план пройден! На все 100%!",
        },
        "tenure_26w": {
            "informal": "Полгода вместе! Спасибо, что ты с нами.",
            "formal": "Полгода совместных занятий. Благодарю за доверие!",
            "schoolchild": "Полгода вместе учимся! Класс!",
        },
        "tenure_52w": {
            "informal": "Год вместе! Это большой путь. Спасибо!",
            "formal": "Год занятий — выдающийся результат. Благодарю!",
            "schoolchild": "Целый год! С днём рождения нашей учёбы!",
        },
        "goal_set": {
            "informal": "Цель поставлена — значит, путь определён!",
            "formal": "Цель сформулирована — движение начинается!",
            "schoolchild": "Цель есть! Теперь вперёд!",
        },
    }
    variants = texts.get(key, {})
    return variants.get(ss, variants.get("informal", ""))


def build_achievement_congrats(key: str, speech_style: str | None = None) -> str:
    """Full congratulation message for a new achievement."""
    a = ACHIEVEMENT_BY_KEY.get(key)
    if not a:
        return ""
    text = _congrats_text(key, speech_style)
    return f"\U0001f3c5 Новое достижение!\n\n{a['icon']} {a['name']}\n{text}"


def build_progress_text(
    progress: dict,
    achievements: list,
    streak_weeks: int,
    is_pair: bool = False,
    pair_title: str | None = None,
    speech_style: str | None = None,
) -> str:
    """Build the full progress screen text."""
    lines: list[str] = []

    if is_pair and pair_title:
        lines.append(f"\U0001f4ca Прогресс пары\n\U0001f465 {pair_title}\n")
    else:
        header = choose_form(
            speech_style or "informal",
            "\U0001f4ca Ваш прогресс",
            "\U0001f4ca Твой прогресс",
            "\U0001f4ca Твой прогресс",
        )
        lines.append(f"{header}\n")

    total = int(progress.get("total_lessons") or 0)
    monthly = int(progress.get("lessons_this_month") or 0)
    lines.append(f"\U0001f4c5 Уроков за этот месяц: {monthly}")
    lines.append(f"\U0001f4c5 Всего уроков: {total}")

    if streak_weeks >= 2:
        lines.append(f"\U0001f525 Без перерывов: {streak_weeks} недель подряд")

    hw_total = int(progress.get("hw_total") or 0)
    hw_done = int(progress.get("hw_done") or 0)
    if hw_total > 0:
        lines.append(f"\U0001f4da ДЗ за этот месяц: {hw_done} из {hw_total} сделано")

    plan_total = int(progress.get("plan_total") or 0)
    plan_done = int(progress.get("plan_done") or 0)
    if plan_total > 0:
        pct = round(plan_done / plan_total * 100)
        lines.append(f"\U0001f4cc Учебный план: {pct}% ✅")

    # Achievements section
    unlocked_keys = {a["achievement_key"] for a in achievements}
    unlocked_count = len(unlocked_keys)
    lines.append(f"\n\U0001f3c5 Достижения ({unlocked_count} / {ACHIEVEMENT_COUNT})\n")

    metrics = {
        "total_lessons": total,
        "streak_weeks": streak_weeks,
        "tenure_weeks": 0,
        "plan_total": plan_total,
        "plan_done": plan_done,
    }
    first_lesson_date = progress.get("first_lesson_date")
    if first_lesson_date:
        from datetime import datetime as dt
        now = dt.now()
        if hasattr(first_lesson_date, "days"):
            pass
        else:
            metrics["tenure_weeks"] = max(0, (now - first_lesson_date).days // 7)

    for a in ACHIEVEMENTS:
        if a["key"] in unlocked_keys:
            lines.append(f"{a['icon']} {a['name']} ✅")
        else:
            remaining_label = a["remaining_label"]
            if callable(remaining_label):
                remaining_label = remaining_label(metrics)
            lines.append(f"⬜ {a['name']} — {remaining_label}")

    return "\n".join(lines)


def build_admin_progress_text(
    progress: dict,
    achievements: list,
    streak_weeks: int,
    feedback: list | None = None,
) -> str:
    """Compact progress block for admin student card."""
    total = int(progress.get("total_lessons") or 0)
    monthly = int(progress.get("lessons_this_month") or 0)
    hw_total = int(progress.get("hw_total") or 0)
    hw_done = int(progress.get("hw_done") or 0)
    plan_total = int(progress.get("plan_total") or 0)
    plan_done = int(progress.get("plan_done") or 0)
    unlocked_count = len(achievements) if achievements else 0

    lines = ["\U0001f4ca <b>Прогресс</b>"]
    lines.append(f"\U0001f4c5 Уроков: {total} ({monthly} за месяц)")
    if streak_weeks >= 2:
        lines.append(f"\U0001f525 Streak: {streak_weeks} нед.")
    if hw_total > 0:
        lines.append(f"\U0001f4da ДЗ за месяц: {hw_done}/{hw_total}")
    if plan_total > 0:
        pct = round(plan_done / plan_total * 100)
        lines.append(f"\U0001f4cc План: {pct}%")
    lines.append(f"\U0001f3c5 Достижения: {unlocked_count}/{ACHIEVEMENT_COUNT}")

    if feedback:
        counts = {"great": 0, "ok": 0, "hard": 0}
        for f in feedback:
            r = f.get("rating") or f
            if isinstance(r, str) and r in counts:
                counts[r] += 1
        parts = []
        if counts["great"]:
            parts.append(f"\U0001f60a×{counts['great']}")
        if counts["ok"]:
            parts.append(f"\U0001f610×{counts['ok']}")
        if counts["hard"]:
            parts.append(f"\U0001f615×{counts['hard']}")
        if parts:
            lines.append(f"\U0001f4ac Фидбэк ({len(feedback)} посл.): {' '.join(parts)}")

    return "\n".join(lines)


def compute_next_milestone(total_lessons: int) -> str | None:
    """If within 3 lessons of a milestone, return text like 'До 25-го урока осталось 3 занятия!'."""
    for ms in LESSON_MILESTONES:
        remaining = ms - total_lessons
        if 1 <= remaining <= 3:
            return f"До {ms}-го урока осталось {remaining}!"
    return None
