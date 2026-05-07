from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from keyboards._helpers import _btn, _url_btn
from utils.speech import speech_style_icon, speech_style_label, speech_style_toggle_label


# ─── Navigation ───────────────────────────────────────────────────────────────

back_to_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("◀️ Главное меню", "back_to_menu")],
])

profile_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🔔 Управление уведомлениями", "notif:manage")],
    [_btn("✉️ Написать преподавателю", "reply:general")],
    [_btn("🧪 Тест уровня", "level_test:now")],
    [_btn("🛡 Опасные действия", "profile:danger")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

def make_parent_profile_keyboard(engagement_mode: str = "active") -> InlineKeyboardMarkup:
    if engagement_mode == "trust":
        mode_label = "🌿 Режим: доверие"
    else:
        mode_label = "🎯 Режим: активное наблюдение"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("👨‍👩‍👧 Открыть детей", "parent:home")],
        [_btn(mode_label, "parent:engagement:toggle")],
        [_btn("✉️ Написать преподавателю", "reply:general")],
        [_btn("🛡 Опасные действия", "profile:danger")],
        [_btn("◀️ Главное меню", "back_to_menu")],
    ])


parent_profile_keyboard = make_parent_profile_keyboard("active")

payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✉️ Сообщить об оплате", "reply:payment"), _btn("💳 Реквизиты", "payment:requisites")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

back_to_admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("◀️ К панели", "admin:home")],
])

cancel_fsm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("❌ Отмена", "cancel_fsm")],
])

# ─── Registration ─────────────────────────────────────────────────────────────

role_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎓 Я ученик", "role:student")],
    [_btn("👥 Мы занимаемся вдвоём", "role:student_pair")],
    [_btn("👨‍👩‍👧 Я родитель ученика", "role:parent")],
])

engagement_mode_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎯 Хочу быть в курсе", "engagement:active")],
    [_btn("🌿 Доверяю преподавателю", "engagement:trust")],
])

level_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("A1 — Начинающий", "level:A1"), _btn("A2 — Элементарный", "level:A2")],
    [_btn("B1 — Средний", "level:B1"), _btn("B2 — Выше среднего", "level:B2")],
    [_btn("C1 — Продвинутый", "level:C1"), _btn("C2 — Мастерство", "level:C2")],
    [_btn("🤷 Не знаю свой уровень", "level:unknown")],
])

# ─── Main menu ────────────────────────────────────────────────────────────────

student_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📅 Расписание", "schedule"), _btn("📚 Домашка", "homework")],
    [_btn("📌 Учебный план", "study_plan"), _btn("💰 Оплата", "payment")],
    [_btn("✉️ Написать преподавателю", "reply:general")],
    [_btn("📁 Материалы", "materials"), _btn("📞 Контакты", "contacts")],
    [_btn("📜 Правила", "work_rules"), _btn("👤 Ещё", "more")],
])

schoolchild_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📅 Расписание", "schedule"), _btn("📚 Домашка", "homework")],
    [_btn("📌 Учебный план", "study_plan")],
    [_btn("✉️ Написать преподавателю", "reply:general")],
    [_btn("📁 Материалы", "materials"), _btn("📞 Контакты", "contacts")],
    [_btn("📜 Правила", "work_rules"), _btn("👤 Ещё", "more")],
])

student_type_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎓 Взрослый", "student_type:adult")],
    [_btn("🎒 Школьник", "student_type:schoolchild")],
])

parent_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👨‍👩‍👧 Мои дети", "parent:home")],
    [_btn("✉️ Написать преподавателю", "reply:general")],
    [_btn("📁 Материалы", "materials"), _btn("📞 Контакты", "contacts")],
    [_btn("📜 Правила", "work_rules"), _btn("👤 Ещё", "more")],
])

student_more_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👤 Профиль", "profile")],
    [_btn("📊 Мой прогресс", "more:progress")],
    [_btn("🔔 Управление уведомлениями", "notif:manage")],
    [_btn("🧪 Тест уровня", "level_test:now")],
    [_btn("❄️ Заморозка", "freeze")],
    [_btn("🛡 Опасные действия", "profile:danger")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

parent_more_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👤 Профиль родителя", "profile")],
    [_btn("🔔 Управление уведомлениями", "notif:manage")],
    [_btn("🛡 Опасные действия", "profile:danger")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

# Backward compatibility for code paths/tests that still import main_keyboard.
main_keyboard = student_main_keyboard

# ─── Progress ────────────────────────────────────────────────────────────────

progress_back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("◀️ Назад", "more")],
])


def make_lesson_feedback_keyboard(lesson_id: int, speech_style: str | None = None) -> InlineKeyboardMarkup:
    ss = speech_style or "informal"
    labels = {
        "informal": ("😊 Отлично", "😐 Нормально", "😕 Сложно"),
        "formal": ("😊 Отлично", "😐 Нормально", "😕 Было сложно"),
        "schoolchild": ("😊 Супер!", "😐 Ок", "😕 Трудновато"),
    }
    great, ok, hard = labels.get(ss, labels["informal"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn(great, f"lesson_feedback:{lesson_id}:great"),
            _btn(ok, f"lesson_feedback:{lesson_id}:ok"),
            _btn(hard, f"lesson_feedback:{lesson_id}:hard"),
        ],
    ])


# ─── Freeze ───────────────────────────────────────────────────────────────────

freeze_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🤒 Болезнь", "freeze:illness")],
    [_btn("✈️ Отпуск", "freeze:vacation")],
    [_btn("⚡ Форс-мажор", "freeze:force_majeure")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

FREEZE_REASON_LABELS = {
    "illness": "Болезнь",
    "vacation": "Отпуск",
    "force_majeure": "Форс-мажор",
}


def make_freeze_confirm_keyboard(reason: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("✅ Отправить заявку", f"freeze_confirm:{reason}"),
        _btn("◀️ Назад", "freeze"),
    ]])


# ─── Homework ─────────────────────────────────────────────────────────────────

def make_homework_filter_keyboard(active_status: str = "active") -> InlineKeyboardMarkup:
    active_label = "• Активные" if active_status == "active" else "📋 Активные"
    done_label = "• Выполненные" if active_status == "done" else "✅ Выполненные"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(active_label, "hw:active"), _btn(done_label, "hw:done")],
        [_btn("◀️ Главное меню", "back_to_menu")],
    ])


def make_notifications_keyboard(reminders: str = "enabled") -> InlineKeyboardMarkup:
    rows = []
    if reminders == "disabled":
        rows.append([_btn("🔔 Включить", "notif:enable")])
    elif reminders.startswith("paused_until:"):
        rows.append([_btn("🔔 Включить раньше", "notif:enable")])
        rows.append([_btn("❌ Отключить полностью", "notif:disable")])
    else:
        rows.append([_btn("🔕 Пауза на неделю", "notif:pause_week")])
        rows.append([_btn("❌ Отключить полностью", "notif:disable")])
    rows.append([_btn("◀️ Назад в профиль", "profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_item_keyboard(hw_id: int, status: str, has_attachment: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([_btn("✅ Отметить как выполненное", f"hw_done:{hw_id}")])
    if has_attachment:
        rows.append([_btn("📎 Открыть файл", f"hw:file:{hw_id}:{status}")])
    rows.append([_btn("✉️ Написать по ДЗ", f"reply:homework:{hw_id}")])
    rows.append([_btn("◀️ К списку ДЗ", f"hw:{status}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_list_keyboard(items: list, status: str) -> InlineKeyboardMarkup:
    rows = []
    active_label = "• Активные" if status == "active" else "📋 Активные"
    done_label = "• Выполненные" if status == "done" else "✅ Выполненные"
    rows.append([
        _btn(active_label, "hw:active"),
        _btn(done_label, "hw:done"),
    ])
    for i, hw in enumerate(items, 1):
        rows.append([_btn(f"📝 {i}. Открыть задание", f"hw:view:{hw['id']}:{status}")])
    if status == "active":
        rows.append([_btn("✉️ Написать по домашке", "reply:homework")])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_parent_home_keyboard(children: list[dict]) -> InlineKeyboardMarkup:
    from utils.ui_text import child_traffic_light
    rows = []
    for child in children:
        icon = child_traffic_light(child)
        rows.append([_btn(f"{icon} {child.get('child_label') or 'Ребёнок'}", f"parent:child:{child['link_id']}")])
    rows.extend(parent_main_keyboard.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_parent_child_keyboard(link_id: int, linked: bool = True, engagement_mode: str = "active") -> InlineKeyboardMarkup:
    rows = []
    if linked:
        if engagement_mode == "trust":
            rows.append([
                _btn("📅 Расписание", f"parent:child:{link_id}:schedule"),
                _btn("💰 Оплаты", f"parent:child:{link_id}:payments"),
            ])
        else:
            rows.append([_btn("📌 Учебный план", f"parent:child:{link_id}:study_plan")])
            rows.append([
                _btn("📅 Расписание", f"parent:child:{link_id}:schedule"),
                _btn("📚 Домашка", f"parent:child:{link_id}:homework:active"),
            ])
            rows.append([_btn("💰 Оплаты", f"parent:child:{link_id}:payments")])
        rows.append([_btn("📊 Прогресс", f"parent:child:{link_id}:progress")])
    rows.append([_btn("✉️ Написать преподавателю", "reply:general")])
    rows.append([_btn("◀️ К детям", "parent:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_parent_homework_keyboard(link_id: int, status: str = "active", items: list | None = None) -> InlineKeyboardMarkup:
    active_label = "• Активные" if status == "active" else "📋 Активные"
    done_label = "• Выполненные" if status == "done" else "✅ Выполненные"
    rows = [[
        _btn(active_label, f"parent:child:{link_id}:homework:active"),
        _btn(done_label, f"parent:child:{link_id}:homework:done"),
    ]]
    for index, hw in enumerate(items or [], start=1):
        rows.append([_btn(f"📝 {index}. Открыть задание", f"parent:child:{link_id}:homework:view:{hw['id']}:{status}")])
    rows.append([_btn("◀️ К ребёнку", f"parent:child:{link_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_parent_homework_item_keyboard(link_id: int, hw_id: int, status: str, has_attachment: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_attachment:
        rows.append([_btn("📎 Открыть файл", f"parent:child:{link_id}:homework:file:{hw_id}:{status}")])
    rows.append([_btn("◀️ К списку ДЗ", f"parent:child:{link_id}:homework:{status}")])
    rows.append([_btn("◀️ К ребёнку", f"parent:child:{link_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_parent_payments_keyboard(link_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✉️ Сообщить об оплате", f"reply:payment:child:{link_id}"), _btn("💳 Реквизиты", f"parent:child:{link_id}:requisites")],
        [_btn("◀️ К ребёнку", f"parent:child:{link_id}")],
    ])


def make_teacher_reply_keyboard(context_key: str, entity_id: int | None = None) -> InlineKeyboardMarkup:
    callback_data = f"reply:{context_key}"
    if entity_id is not None:
        callback_data += f":{entity_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✉️ Ответить преподавателю", callback_data)],
    ])


def make_reschedule_offer_keyboard(slot_tokens: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[_btn(f"🗓 {label}", f"reschedule_pick:{token}")] for token, label in slot_tokens]
    rows.append([_btn("✉️ Написать преподавателю", "reply:broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_lesson_presence_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✅ Буду вовремя", f"lesson_presence:on_time:{lesson_id}"),
            _btn("⏱ Немного задержусь", f"lesson_presence:late:{lesson_id}"),
        ],
        [_btn("✉️ Написать преподавателю", f"reply:lesson:{lesson_id}")],
    ])


def make_lesson_followup_keyboard(lesson_id: int, student_id: int, *, balance: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [_btn("💬 Комментарий по уроку", f"lesson_followup:comment:{lesson_id}")],
        [_btn("📖 Сохранить закладку", f"lesson_followup:bookmark:{lesson_id}:{student_id}")],
        [_btn("🚫 Без учебника/книги", f"lesson_followup:no_material:{lesson_id}:{student_id}")],
        [_btn("⚠️ Прогул — списать", f"lesson_followup:no_show:{lesson_id}:{student_id}")],
    ]
    if balance <= 0:
        rows.append([_btn("💳 Внести оплату", f"lesson_followup:payment:{student_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── User reference screens ───────────────────────────────────────────────────

def make_contacts_keyboard(
    booking_url: str = "",
    vk_call_url: str = "",
    google_meet_url: str = "",
    website_url: str = "",
) -> InlineKeyboardMarkup:
    rows = []
    if vk_call_url:
        rows.append([_url_btn("📞 VK Звонок", vk_call_url)])
    if google_meet_url:
        rows.append([_url_btn("📹 Google Meet (VPN)", google_meet_url)])
    if booking_url:
        rows.append([_url_btn("📝 Записаться на урок", booking_url)])
    if website_url:
        rows.append([_url_btn("↗️ Сайт преподавателя", website_url)])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_schedule_keyboard(calendar_url: str = "") -> InlineKeyboardMarkup:
    rows = []
    if calendar_url:
        rows.append([_url_btn("🗓 Открыть Google Calendar", calendar_url)])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_materials_keyboard(
    resources: list | None = None,
    *,
    website_url: str = "",
) -> InlineKeyboardMarkup:
    """Render the «Материалы» screen keyboard.

    Each resource becomes a URL-button. Primary first, then globals, then per-student.
    Falls back to optional `website_url` button when there are no resources.
    """
    from utils.resource_provider import provider_emoji
    from aiogram.types import InlineKeyboardButton

    items = list(resources or [])
    rows: list[list[InlineKeyboardButton]] = []

    if items:
        primary = next((r for r in items if r.get("is_primary")), None)
        rest = [r for r in items if r is not primary]
        ordered = ([primary] if primary else []) + rest
        for r in ordered:
            emoji = provider_emoji(r.get("provider") or "other")
            label = (r.get("label") or "Открыть").strip()
            text = f"{emoji} {label}"
            if primary and r is primary:
                text = f"⭐ {text}"
            rows.append([_url_btn(text[:64], r["url"])])
    elif website_url:
        rows.append([_url_btn("↗️ Сайт преподавателя", website_url)])

    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_first_lesson_invite_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("💳 Реквизиты", "requisites")],
        [_btn("💰 Открыть раздел оплаты", "payment")],
        [_btn("✉️ Сообщить об оплате", "reply:payment")],
    ])


def make_back_button_keyboard(label: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(label, callback_data)],
    ])
