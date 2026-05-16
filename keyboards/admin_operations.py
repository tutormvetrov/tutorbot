from __future__ import annotations

from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardMarkup
from keyboards._helpers import _btn, _url_btn


# ─── Homework CRUD ────────────────────────────────────────────────────────────

def make_homework_delete_keyboard(items: list) -> InlineKeyboardMarkup:
    rows = []
    for i, hw in enumerate(items, 1):
        deadline_str = hw["deadline"].strftime("%d.%m.%Y") if hw.get("deadline") else "—"
        label = f"📝 {i}. {hw['full_name']} · до {deadline_str}"
        if hw.get("queued_deliver_after"):
            delivery_str = hw["queued_deliver_after"].strftime("%H:%M")
            label += f" · 📨 {delivery_str}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"admin:homework_manage:{hw['id']}")])
    rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_manage_actions_keyboard(hw_id: int, *, can_send_now: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_btn("✏️ Редактировать", f"hw_edit_start:{hw_id}")],
        [_btn("🗑 Удалить", f"hw_delete_confirm:{hw_id}")],
    ]
    if can_send_now:
        rows.insert(1, [_btn("📨 Отправить сейчас", f"hw_send_now:{hw_id}")])
    rows.append([_btn("◀️ К активным ДЗ", "admin:all_homework")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_delivery_result_keyboard(hw_id: int, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📨 Отправить сейчас", f"hw_send_now:{hw_id}")],
        [_btn("📚 Открыть карточку ДЗ", f"admin:homework_manage:{hw_id}")],
        [_btn("◀️ Вернуться", back_callback)],
    ])


def make_homework_sent_now_keyboard(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📚 К карточке ДЗ", f"admin:homework_manage:{hw_id}")],
        [_btn("◀️ К активным ДЗ", "admin:all_homework")],
    ])


def make_homework_delete_confirm_keyboard(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("🗑 Удалить ДЗ", f"hw_delete:{hw_id}"),
        _btn("❌ Отмена", "admin:all_homework"),
    ]])


def make_homework_edit_content_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("⏭ Оставить текущий текст и файл", "hw_edit_keep_content")],
        [_btn("❌ Отмена", "cancel_fsm")],
    ])


def make_homework_edit_deadline_keyboard(current_deadline: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"⏭ Оставить дедлайн {current_deadline}", "hw_edit_keep_deadline")],
        [_btn("❌ Отмена", "cancel_fsm")],
    ])


# ─── Lessons + calendar aliases ───────────────────────────────────────────────

def make_lessons_manage_keyboard(lessons: list) -> InlineKeyboardMarkup:
    rows = []
    status_icons = {"active": "✅", "frozen": "❄️", "freeze_pending": "⏳"}
    for lesson in lessons:
        date_str = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else '—'
        icon = status_icons.get(lesson['status'], "•")
        rows.append([_btn(f"{icon} {date_str}", f"lesson_delete_confirm:{lesson['id']}")])
    rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_lesson_delete_confirm_keyboard(lesson_id: int, can_delete_from_calendar: bool = False) -> InlineKeyboardMarkup:
    rows = [[_btn("🗑 Удалить только из бота", f"lesson_delete:{lesson_id}:db")]]
    if can_delete_from_calendar:
        rows.append([_btn("🗓 Удалить из бота и Calendar", f"lesson_delete:{lesson_id}:calendar")])
    rows.append([_btn("❌ Отмена", "admin:manage_lessons")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_calendar_alias_student_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        count = student.get("alias_count", 0)
        label = f"{student['full_name']} ({count})" if count else student["full_name"]
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"calendar_alias_student:{student['telegram_id']}")])
    rows.append([_btn("◀️ К сервису", "admin:cat:service")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_calendar_alias_editor_keyboard(student_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Очистить правила", f"calendar_aliases:clear:{student_id}")],
        [_btn("◀️ К списку учеников", "admin:calendar_aliases")],
        [_btn("❌ Отмена", "cancel_fsm")],
    ])


# ─── Resources ────────────────────────────────────────────────────────────────

def _truncate_resource_label(label: str, max_len: int = 28) -> str:
    label = (label or "").strip() or "(без названия)"
    if len(label) <= max_len:
        return label
    return label[: max_len - 1] + "…"


def make_admin_student_resources_keyboard(
    telegram_id: int,
    page: int,
    resources: list,
) -> InlineKeyboardMarkup:
    """Per-student resources management screen.

    `resources` lists only entries with `student_id == telegram_id` (no globals).
    """
    from utils.resource_provider import provider_emoji
    from aiogram.types import InlineKeyboardButton

    rows: list[list[InlineKeyboardButton]] = []
    for r in resources:
        emoji = provider_emoji(r.get("provider") or "other")
        prefix = "⭐ " if r.get("is_primary") else ""
        label = _truncate_resource_label(r.get("label") or "")
        rows.append([
            _url_btn(f"{prefix}{emoji} {label}", r["url"]),
        ])
        action_row = []
        if not r.get("is_primary"):
            action_row.append(_btn("⭐ Сделать основной", f"admin:resources:set_primary:{r['id']}:{telegram_id}:{page}"))
        action_row.append(_btn("🗑 Удалить", f"admin:resources:delete:{r['id']}:{telegram_id}:{page}"))
        rows.append(action_row)
    rows.append([_btn("➕ Добавить ссылку", f"admin:resources:add:{telegram_id}:{page}")])
    rows.append([_btn("🌍 Глобальные ссылки", "admin:resources:global")])
    rows.append([_btn("◀️ К действиям", f"admin:student_actions:{telegram_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_global_resources_keyboard(resources: list, *, back_callback: str = "admin:cat:service") -> InlineKeyboardMarkup:
    from utils.resource_provider import provider_emoji
    from aiogram.types import InlineKeyboardButton

    rows: list[list[InlineKeyboardButton]] = []
    for r in resources:
        emoji = provider_emoji(r.get("provider") or "other")
        prefix = "⭐ " if r.get("is_primary") else ""
        label = _truncate_resource_label(r.get("label") or "")
        rows.append([_url_btn(f"{prefix}{emoji} {label}", r["url"])])
        action_row = []
        if not r.get("is_primary"):
            action_row.append(_btn("⭐ Сделать основной", f"admin:resources:set_primary:{r['id']}:global:0"))
        action_row.append(_btn("🗑 Удалить", f"admin:resources:delete:{r['id']}:global:0"))
        rows.append(action_row)
    rows.append([_btn("➕ Добавить глобальную ссылку", "admin:resources:add:global:0")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_resource_primary_choice_keyboard(
    *,
    yes_callback: str,
    no_callback: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("⭐ Сделать основной", yes_callback)],
        [_btn("➡️ Не сейчас", no_callback)],
    ])


# ─── Nudge ────────────────────────────────────────────────────────────────────

def make_nudge_keyboard(student_id: int, nudge_id: int, stage: int) -> InlineKeyboardMarkup:
    """Inline keyboard for homework nudge messages (3-stage escalation)."""
    rows = [[_btn("📝 Отправить ДЗ", f"nudge:hw:{student_id}")]]
    if stage >= 2:
        rows.append([_btn("⏭ Пропустить", f"nudge:skip:{nudge_id}")])
    if stage >= 3:
        rows.append([_btn("💤 Урок был без ДЗ", f"nudge:nohw:{nudge_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Work rules ──────────────────────────────────────────────────────────────

def make_work_rules_admin_keyboard(rules: list) -> InlineKeyboardMarkup:
    rows = []
    for rule in rules:
        rows.append([_btn(f"✏️ {rule['title']}", f"admin:work_rule:edit:{rule['id']}")])
    rows.append([_btn("➕ Добавить правило", "admin:work_rule:add")])
    if rules:
        rows.append([_btn("📤 Разослать правила", "admin:work_rule:broadcast")])
    rows.append([_btn("◀️ К сервису", "admin:cat:service")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


work_rules_broadcast_confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✅ Отправить всем", "admin:work_rule:broadcast:confirm")],
    [_btn("◀️ Назад", "admin:work_rules")],
])


def make_work_rule_edit_keyboard(rule_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✏️ Заголовок", f"admin:work_rule:edit_title:{rule_id}")],
        [_btn("✏️ Текст", f"admin:work_rule:edit_body:{rule_id}")],
        [_btn("🗑 Удалить", f"admin:work_rule:delete:{rule_id}")],
        [_btn("◀️ К правилам", "admin:work_rules")],
    ])


work_rules_view_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("◀️ Главное меню", "back_to_menu")],
])

work_rules_onboarding_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✅ Ознакомлен(а)", "work_rules:accept")],
])


# ─── No-show ─────────────────────────────────────────────────────────────────

def make_no_show_confirm_keyboard(lesson_id: int, student_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✅ Списать", f"no_show:confirm:{lesson_id}:{student_id}"),
            _btn("❌ Отмена", f"no_show:cancel:{lesson_id}:{student_id}"),
        ],
    ])


def make_no_show_lessons_keyboard(lessons: list, student_id: int, page: int) -> InlineKeyboardMarkup:
    rows = []
    for lesson in lessons:
        ld = lesson.get("lesson_date")
        date_str = ld.strftime("%d.%m %H:%M") if ld else "—"
        rows.append([_btn(f"📅 {date_str}", f"admin:no_show:pick:{lesson['id']}:{student_id}:{page}")])
    rows.append([_btn("◀️ К действиям", f"admin:student_actions:{student_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Payment auto-calc ───────────────────────────────────────────────────────

def make_payment_autoconfirm_keyboard(student_id: int, amount: float, lessons: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✅ Подтвердить", f"payment_auto:confirm:{student_id}:{amount}:{lessons}"),
            _btn("✏️ Изменить кол-во", f"payment_auto:edit:{student_id}:{amount}"),
        ],
        [_btn("❌ Отмена", "cancel_fsm")],
    ])
