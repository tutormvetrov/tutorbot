from __future__ import annotations

import json
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards._helpers import _btn, _url_btn
from utils.brand import BRAND_TONE_LABELS
from utils.speech import speech_style_icon


# ─── Admin nav ────────────────────────────────────────────────────────────────

admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎯 Сегодня", "admin:today"), _btn("📊 Пульс", "admin:pulse")],
    [_btn("👥 Ученики", "admin:cat:students"), _btn("📚 Учебный процесс", "admin:cat:education")],
    [_btn("💰 Финансы", "admin:finance"), _btn("📢 Рассылка", "admin:broadcast")],
    [_btn("💬 Входящие", "admin:inbox"), _btn("⚙️ Сервис", "admin:cat:service")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

admin_students_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📋 Список учеников", "admin:students"), _btn("👨‍👩‍👧 Родители", "admin:parents")],
    [_btn("👥 Пары", "admin:pairs"), _btn("👤 Добавить ученика", "admin:add_student")],
    [_btn("◀️ К панели", "back_to_admin")],
])

def make_admin_education_keyboard(pending_freeze_count: int = 0) -> InlineKeyboardMarkup:
    freeze_label = f"❄️ Заявки на заморозку ({pending_freeze_count})" if pending_freeze_count else "❄️ Заявки на заморозку"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📅 Уроки: добавить / удалить", "admin:cat:education:lessons")],
        [_btn("📚 ДЗ: задать / активные", "admin:cat:education:homework")],
        [_btn(freeze_label, "admin:freezes")],
        [_btn("◀️ К панели", "back_to_admin")],
    ])


# Keep a static default for backwards compatibility in imports.
admin_education_keyboard = make_admin_education_keyboard(0)

admin_service_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🏥 Здоровье бота", "admin:health")],
    [_btn("💬 Касания: настройки", "admin:touches:settings")],
    [_btn("🔄 Синхронизация Calendar", "admin:sync:service")],
    [_btn("🧭 Алиасы Calendar", "admin:calendar_aliases")],
    [_btn("📋 Отчёт синхронизации", "admin:calendar_report")],
    [_btn("🎨 Тональность бренда", "admin:brand_tone")],
    [_btn("📜 Правила работы", "admin:work_rules")],
    [_btn("📝 Рабочие заметки", "admin:notes")],
    [_btn("🌍 Глобальные учебные ссылки", "admin:resources:global")],
    [_btn("🔄 Пересчитать достижения", "admin:service:backfill_achievements")],
    [_btn("🧪 Просмотр ролей", "admin:preview")],
    [_btn("🔄 Перезапуск бота", "admin:restart")],
    [_btn("◀️ К панели", "back_to_admin")],
])

broadcast_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🤒 Заболел — возможен перенос", "broadcast:illness")],
    [_btn("⚡ Форс-мажор — возможен перенос", "broadcast:force_majeure")],
    [_btn("🧪 Пригласить на тест уровня", "broadcast:level_test")],
    [_btn("✏️ Своё сообщение", "broadcast:custom")],
    [_btn("◀️ К панели", "back_to_admin")],
])


broadcast_preview_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✅ К выбору получателей", "bc_confirm")],
    [_btn("✏️ Изменить сообщение", "bc_edit_text")],
    [_btn("❌ Отмена", "cancel_fsm")],
])


# ─── Broadcast/segmentation ───────────────────────────────────────────────────

_STAGE_LABELS = {"new": "🆕 Новый", "regular": "📗 Основной", "veteran": "🏅 Давний"}
_BALANCE_LABELS = {"has": "💰 Есть", "low": "Мало (1–2)", "none": "Нет"}
_FORMAT_LABELS = {"online": "💻 Онлайн", "offline": "Офлайн"}
_TYPE_LABELS = {"solo": "👤 Один", "pair": "👥 Пара"}


def segment_filter_keyboard(filters: dict, count: int) -> InlineKeyboardMarkup:
    def _toggle(label: str, cat: str, val: str) -> dict:
        mark = "✅" if val in filters.get(cat, []) else "☐"
        return _btn(f"{mark} {label}", f"bc_filter:{cat}:{val}")

    rows = [
        [_toggle(lbl, "stages", v) for v, lbl in _STAGE_LABELS.items()],
        [_toggle(v, "levels", v) for v in ("A1", "A2", "B1", "B2", "C1", "C2")],
        [_toggle(lbl, "formats", v) for v, lbl in _FORMAT_LABELS.items()],
        [_toggle(lbl, "balance", v) for v, lbl in _BALANCE_LABELS.items()],
        [_toggle(lbl, "types", v) for v, lbl in _TYPE_LABELS.items()],
        [_btn("✖️ Сбросить", "bc_filter:reset"), _btn(f"📤 Показать {count} чел. →", "bc_filter:apply")],
        [_btn("Без фильтров → все ученики", "bc_filter:skip")],
        [_btn("◀️ К предпросмотру", "bc_back_preview"), _btn("❌ Отмена", "cancel_fsm")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_recipient_select_keyboard(students: list, selected_ids: set) -> InlineKeyboardMarkup:
    rows = []
    for s in students:
        mark = "✅" if s["telegram_id"] in selected_ids else "☐"
        rows.append([_btn(f"{mark} {s['full_name']}", f"bc_toggle:{s['telegram_id']}")])
    rows.append([_btn("☑️ Все", "bc_all"), _btn("✖️ Никто", "bc_none")])
    count = len(selected_ids)
    if count:
        rows.append([_btn(f"📤 Отправить ({count})", "bc_send")])
    rows.append([_btn("◀️ К предпросмотру", "bc_back_preview")])
    rows.append([_btn("❌ Отмена", "cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Parents ──────────────────────────────────────────────────────────────────

def make_admin_parents_list_keyboard(
    parents: list,
    page: int,
    page_size: int,
    has_query: bool = False,
) -> InlineKeyboardMarkup:
    rows = [[_btn("🔎 Поиск: имя или ID", "admin:parents:search")]]
    if has_query:
        rows[0].append(_btn("✖️ Очистить поиск", "admin:parents:search_clear"))

    start = page * page_size
    page_items = parents[start:start + page_size]

    for offset, parent in enumerate(page_items, start=1):
        index = start + offset
        label = f"{index}. {parent['full_name']}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"admin:parent_card:{parent['telegram_id']}:{page}")])

    total_pages = max(1, (len(parents) + page_size - 1) // page_size)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("⬅️", f"admin:parents:page:{page - 1}"))
        nav_row.append(_btn(f"Стр. {page + 1}/{total_pages}", f"admin:parents:page:{page}"))
        if page < total_pages - 1:
            nav_row.append(_btn("➡️", f"admin:parents:page:{page + 1}"))
        rows.append(nav_row)

    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_parent_card_keyboard(telegram_id: int, page: int, children: list[dict] | None = None) -> InlineKeyboardMarkup:
    rows = []
    if children:
        for child in children:
            if child.get("link_status") == "linked" and child.get("student_id"):
                child_name = child.get("full_name") or child.get("student_info") or "?"
                link_id = child.get("link_id") or child.get("id")
                rows.append([
                    _btn(f"💳 Тариф: {child_name}", f"admin:student_tariff:{child['student_id']}:0"),
                    _btn("✕", f"admin:parent:unlink:{link_id}:{telegram_id}:{page}"),
                ])
    rows.append([_btn("➕ Привязать ученика", f"admin:parent:link_student:{telegram_id}:{page}")])
    rows.append([_btn("🪟 Открыть как родитель", f"admin:parent_preview_select:{telegram_id}:{page}")])
    rows.append([_btn("🛡 Опасные действия", f"admin:parent_danger:{telegram_id}:{page}")])
    rows.append([_btn("◀️ К списку родителей", f"admin:parents:page:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_parent_danger_keyboard(telegram_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Деактивировать", f"admin:parent_deactivate_prompt:{telegram_id}:{page}")],
        [_btn("💀 Удалить навсегда", f"admin:parent_delete_prompt:{telegram_id}:{page}")],
        [_btn("◀️ К карточке родителя", f"admin:parent_card:{telegram_id}:{page}")],
    ])


def make_admin_lesson_formats_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        lesson_format = (student.get("lesson_format") or "online").strip().lower()
        is_offline = lesson_format == "offline"
        icon = "🏠" if is_offline else "💻"
        target = "online" if is_offline else "offline"
        target_label = "в онлайн" if is_offline else "в очно"
        label = f"{icon} {student['full_name']} · переключить {target_label}"
        if len(label) > 64:
            label = label[:62] + "…"
        rows.append([_btn(label, f"admin:lesson_format_toggle:{student['telegram_id']}:{target}")])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_speech_styles_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        current_style = (student.get("speech_style") or "formal").strip().lower()
        target = "informal" if current_style == "formal" else "formal"
        target_label = "на ты" if current_style == "formal" else "на Вы"
        label = f"{speech_style_icon(current_style)} {student['full_name']} · переключить {target_label}"
        if len(label) > 64:
            label = label[:62] + "…"
        rows.append([_btn(label, f"admin:speech_style_toggle:{student['telegram_id']}:{target}")])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Admin payments ───────────────────────────────────────────────────────────

def make_payment_delete_keyboard(student_id: int, payments: list, page: int | None = None, source: str = "card", balance: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if balance < 0:
        writeoff_cb = f"admin:balance_writeoff_ask:{student_id}"
        if page is not None:
            writeoff_cb += f":{page}:{source}"
        rows.append([_btn(f"🔄 Обнулить баланс ({balance})", writeoff_cb)])
    for i, payment in enumerate(payments, 1):
        date_str = payment["payment_date"].strftime("%d.%m.%Y") if payment.get("payment_date") else "—"
        callback = f"payment_delete_confirm:{student_id}:{payment['id']}"
        if page is not None:
            callback += f":{page}:{source}"
        rows.append([
            _btn(
                f"🗑 {i}. {int(payment['amount'])} ₽ · {date_str}",
                callback,
            )
        ])
    if page is not None:
        back_view = f"admin:student_{source}:{student_id}:{page}" if source in {"actions", "settings", "danger"} else f"admin:student_card:{student_id}:{page}"
        rows.append([_btn("◀️ Назад", back_view)])
    else:
        rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_payment_delete_confirm_keyboard(student_id: int, payment_id: int, page: int | None = None, source: str = "card") -> InlineKeyboardMarkup:
    delete_callback = f"payment_delete:{student_id}:{payment_id}"
    cancel_callback = f"admin:student_payments:{student_id}"
    if page is not None:
        delete_callback += f":{page}:{source}"
        cancel_callback += f":{page}:{source}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("🗑 Удалить оплату", delete_callback),
        _btn("❌ Отмена", cancel_callback),
    ]])


def make_balance_writeoff_confirm_keyboard(student_id: int, page: int | None = None, source: str = "card") -> InlineKeyboardMarkup:
    confirm_cb = f"admin:balance_writeoff_do:{student_id}"
    cancel_cb = f"admin:student_payments:{student_id}"
    if page is not None:
        confirm_cb += f":{page}:{source}"
        cancel_cb += f":{page}:{source}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("✅ Обнулить", confirm_cb),
        _btn("❌ Отмена", cancel_cb),
    ]])


# ─── Admin context/confirm ────────────────────────────────────────────────────

def make_admin_context_keyboard(student_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("◀️ Вернуться к карточке ученика", f"admin:student_card:{student_id}:{page}")],
        [_btn("◀️ К списку учеников", f"admin:students:page:{page}")],
    ])


def make_admin_student_danger_confirm_keyboard(confirm_callback: str, cancel_callback: str, confirm_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(confirm_text, confirm_callback)],
        [_btn("❌ Отмена", cancel_callback)],
    ])


def make_admin_student_danger_review_keyboard(review_callback: str, cancel_callback: str, review_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(review_text, review_callback)],
        [_btn("❌ Отмена", cancel_callback)],
    ])


def make_student_select_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = [
        [_btn(s["full_name"], f"select_student:{s['telegram_id']}")]
        for s in students
    ]
    rows.append([_btn("❌ Отмена", "cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Admin notes ──────────────────────────────────────────────────────────────

admin_notes_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("➕ Новая заметка", "admin:notes:add")],
    [_btn("🧹 Очистить ленту", "admin:notes:clear")],
    [_btn("◀️ К сервису", "admin:cat:service")],
])


# ─── Admin config ─────────────────────────────────────────────────────────────

def make_brand_tone_keyboard(current_tone: str, back_callback: str = "admin:cat:service") -> InlineKeyboardMarkup:
    rows = []
    for tone, label in BRAND_TONE_LABELS.items():
        prefix = "• " if tone == current_tone else ""
        rows.append([_btn(f"{prefix}{label.capitalize()}", f"admin:brand_tone_set:{tone}")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_today_keyboard(snapshot: dict) -> InlineKeyboardMarkup:
    pending_freeze: int = int(snapshot.get("pending_freeze_count") or 0)
    freeze_label = f"❄️ Заявки на заморозку ({pending_freeze})" if pending_freeze else "❄️ Заявки на заморозку"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📅 Открыть расписание дня", "admin:today:lessons")],
        [_btn("💰 Кому отправить реквизиты", "admin:today:unpaid"), _btn("📚 Кому задать ДЗ", "admin:today:missing_hw")],
        [_btn(freeze_label, "admin:freezes"), _btn("💬 Ответы учеников", "admin:inbox")],
        [_btn("◀️ К панели", "admin:home")],
    ])


# ─── Admin Inbox ──────────────────────────────────────────────────────────────

_KIND_LABELS: dict[str, str] = {
    "reply": "по сообщению",
    "freeze_request": "заморозка",
    "first_contact": "новый родитель",
}


def _inbox_event_label(event) -> str:
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    name = (payload.get("full_name") or "—")
    if len(name) > 15:
        name = name[:14] + "…"
    context = payload.get("context") or event.get("kind") or "—"
    context_labels = {
        "homework": "по ДЗ",
        "payment": "по оплате",
        "general": "общий",
        "freeze": "заморозка",
        "lesson": "по уроку",
        "broadcast": "по рассылке",
        "teacher_message": "по сообщению",
        "review": "по отзыву",
        "first_contact": "новый родитель",
    }
    context_label = context_labels.get(context, context)
    created_at = event.get("created_at")
    if isinstance(created_at, datetime):
        time_str = created_at.strftime("%H:%M")
    else:
        time_str = "—"
    handled = event.get("handled_at")
    prefix = "📨" if handled else "🆕"
    return f"{prefix} {time_str} · {name} ({context_label})"


def make_admin_inbox_keyboard(events: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    today_events = []
    yesterday_events = []
    older_events = []

    now = datetime.now()
    today_date = now.date()
    yesterday_date = today_date - timedelta(days=1)

    for event in events:
        created_at = event.get("created_at")
        if isinstance(created_at, datetime):
            event_date = created_at.date()
        else:
            event_date = None

        if event_date == today_date:
            today_events.append(event)
        elif event_date == yesterday_date:
            yesterday_events.append(event)
        else:
            older_events.append(event)

    if today_events:
        rows.append([_btn("🆕 Сегодня", "admin:inbox:noop")])
        for event in today_events:
            rows.append([_btn(_inbox_event_label(event), f"admin:inbox:item:{event['id']}")])

    if yesterday_events:
        rows.append([_btn("📬 Вчера", "admin:inbox:noop")])
        for event in yesterday_events:
            rows.append([_btn(_inbox_event_label(event), f"admin:inbox:item:{event['id']}")])

    if older_events:
        rows.append([_btn("📁 Ранее", "admin:inbox:noop")])
        for event in older_events:
            rows.append([_btn(_inbox_event_label(event), f"admin:inbox:item:{event['id']}")])

    if not events:
        rows.append([_btn("✅ Нет непрочитанных", "admin:inbox:noop")])

    rows.append([_btn("✓ Отметить всё прочитанным", "admin:inbox:mark_all_read")])
    rows.append([_btn("◀️ К панели", "admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_inbox_item_keyboard(event_id: int, kind: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([_btn("✉️ Ответить", f"admin:inbox:reply:{event_id}")])
    rows.append([_btn("✓ Закрыть", f"admin:inbox:item:{event_id}:close")])
    rows.append([_btn("◀️ К входящим", "admin:inbox")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Pulse/briefing ───────────────────────────────────────────────────────────

_PULSE_COLOR_EMOJI = {"red": "\U0001f534", "yellow": "\U0001f7e1", "green": "\U0001f7e2"}


def make_pulse_keyboard(health_list: list[dict]) -> InlineKeyboardMarkup:
    """Inline keyboard for the Pulse dashboard: each student is a clickable button."""
    rows = []
    for h in health_list:
        emoji = _PULSE_COLOR_EMOJI.get(h.get("color", "green"), "⬜")
        name = h.get("pair_title") if h.get("is_pair") else h.get("full_name", "---")
        tid = h.get("telegram_id")
        if tid:
            rows.append([_btn(f"{emoji} {name}", f"pulse:student:{tid}")])
    rows.append([_btn("◀️ К панели", "admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_briefing_keyboard(most_urgent_student_id: int | None = None) -> InlineKeyboardMarkup:
    """Inline keyboard for the morning briefing message."""
    rows = [[_btn("📊 Пульс", "briefing:pulse")]]
    if most_urgent_student_id:
        rows.append([_btn("📝 Отправить ДЗ", f"briefing:hw:{most_urgent_student_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Finance ─────────────────────────────────────────────────────────────────

finance_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("💰 Оплаты: добавить / просмотреть", "admin:finance:payments")],
    [_btn("💳 Тарифы", "admin:pricing")],
    [_btn("◀️ К панели", "back_to_admin")],
])
