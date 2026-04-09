from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.brand import BRAND_TONE_LABELS
from utils.speech import speech_style_icon, speech_style_label, speech_style_toggle_label


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


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

parent_profile_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👨‍👩‍👧 Открыть детей", "parent:home")],
    [_btn("✉️ Написать преподавателю", "reply:general")],
    [_btn("🛡 Опасные действия", "profile:danger")],
    [_btn("◀️ Главное меню", "back_to_menu")],
])

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
    [_btn("👨‍👩‍👧 Я родитель ученика", "role:parent")],
])

level_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("A1 — Начинающий", "level:A1"), _btn("A2 — Элементарный", "level:A2")],
    [_btn("B1 — Средний", "level:B1"), _btn("B2 — Выше среднего", "level:B2")],
    [_btn("C1 — Продвинутый", "level:C1"), _btn("C2 — Мастерство", "level:C2")],
    [_btn("🤷 Не знаю свой уровень", "level:unknown")],
])

# ─── Main menu ────────────────────────────────────────────────────────────────

student_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📅 Расписание", "schedule"), _btn("📚 Домашние задания", "homework")],
    [_btn("❄️ Заморозка", "freeze"), _btn("💰 Оплата", "payment")],
    [_btn("👤 Профиль", "profile"), _btn("📞 Контакты", "contacts")],
    [_btn("💳 Реквизиты", "requisites"), _btn("✉️ Написать преподавателю", "reply:general")],
])

parent_main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👨‍👩‍👧 Мои дети", "parent:home"), _btn("✉️ Написать преподавателю", "reply:general")],
    [_btn("👤 Профиль", "profile"), _btn("📞 Контакты", "contacts")],
    [_btn("💳 Реквизиты", "requisites")],
])

# Backward compatibility for code paths/tests that still import main_keyboard.
main_keyboard = student_main_keyboard

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
    rows = []
    for child in children:
        icon = "✅" if child.get("link_status") == "linked" else "⏳"
        rows.append([_btn(f"{icon} {child.get('child_label') or 'Ребёнок'}", f"parent:child:{child['link_id']}")])
    rows.extend(parent_main_keyboard.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_parent_child_keyboard(link_id: int, linked: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if linked:
        rows.append([
            _btn("📅 Расписание", f"parent:child:{link_id}:schedule"),
            _btn("📚 Домашка", f"parent:child:{link_id}:homework:active"),
        ])
        rows.append([_btn("💰 Оплаты", f"parent:child:{link_id}:payments")])
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
        [_btn("✉️ Сообщить об оплате", "reply:payment")],
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


def make_lesson_followup_keyboard(lesson_id: int, student_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("💬 Комментарий по уроку", f"lesson_followup:comment:{lesson_id}")],
        [_btn("📖 Сохранить закладку", f"lesson_followup:bookmark:{lesson_id}:{student_id}")],
        [_btn("🚫 Без учебника/книги", f"lesson_followup:no_material:{lesson_id}:{student_id}")],
    ])


# ─── Admin ────────────────────────────────────────────────────────────────────

admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("👥 Ученики", "admin:cat:students"), _btn("📚 Учебный процесс", "admin:cat:education")],
    [_btn("📢 Рассылка", "admin:broadcast"), _btn("⚙️ Сервис", "admin:cat:service")],
    [_btn("🧪 Просмотр ролей", "admin:preview"), _btn("◀️ Главное меню", "back_to_menu")],
])

admin_students_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📋 Список учеников", "admin:students"), _btn("👨‍👩‍👧 Родители", "admin:parents")],
    [_btn("👤 Добавить ученика", "admin:add_student"), _btn("🏫 Формат занятий", "admin:lesson_formats")],
    [_btn("🗣 Обращение", "admin:speech_styles"), _btn("🗑 Деактивировать", "admin:deactivate_student")],
    [_btn("💀 Полный сброс", "admin:delete_student")],
    [_btn("◀️ К панели", "back_to_admin")],
])

admin_education_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("➕ Добавить занятие", "admin:add_lesson:education"), _btn("🗑 Удалить занятие", "admin:manage_lessons")],
    [_btn("💳 Добавить оплату", "admin:add_payment:education"), _btn("❄️ Заморозки", "admin:freezes")],
    [_btn("📚 Задать ДЗ", "admin:add_homework:education"), _btn("📋 Активные ДЗ", "admin:all_homework")],
    [_btn("◀️ К панели", "back_to_admin")],
])

admin_service_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("📊 Мониторинг", "admin:service:monitoring")],
    [_btn("🧠 Контекст и проект", "admin:service:context")],
    [_btn("◀️ К панели", "back_to_admin")],
])

admin_service_monitoring_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🔄 Синхронизация Calendar", "admin:sync:monitoring")],
    [_btn("🧭 Алиасы Calendar", "admin:calendar_aliases")],
    [_btn("📋 Отчёт синхронизации", "admin:calendar_report")],
    [_btn("🏥 Здоровье бота", "admin:health")],
    [_btn("◀️ К сервису", "admin:cat:service")],
])

admin_service_context_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("🎨 Тональность бренда", "admin:brand_tone")],
    [_btn("📝 Сообщения для отладки", "admin:notes")],
    [_btn("◀️ К сервису", "admin:cat:service")],
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


def make_deactivate_review_keyboard(student_id: int, cancel_callback: str = "back_to_admin") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("⚠️ Перейти к подтверждению", f"deactivate_review:{student_id}")],
        [_btn("❌ Отмена", cancel_callback)],
    ])


def make_deactivate_confirm_keyboard(student_id: int, cancel_callback: str = "back_to_admin") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("✅ Деактивировать", f"deactivate_confirm:{student_id}"),
        _btn("❌ Отмена", cancel_callback),
    ]])


def make_delete_review_keyboard(student_id: int, cancel_callback: str = "back_to_admin") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("⚠️ Перейти к подтверждению", f"delete_review:{student_id}")],
        [_btn("❌ Отмена", cancel_callback)],
    ])


def make_delete_confirm_keyboard(student_id: int, cancel_callback: str = "back_to_admin") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        _btn("💀 Удалить навсегда", f"delete_confirm:{student_id}"),
        _btn("❌ Отмена", cancel_callback),
    ]])


def make_freeze_action_keyboard(lesson_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✅ Одобрить", f"freeze_action:approve:{lesson_id}"),
            _btn("❌ Отклонить", f"freeze_action:reject:{lesson_id}"),
        ],
        [_btn("◀️ К заявкам", "admin:freezes")],
    ])


def make_freeze_queue_keyboard(lesson_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [[
        _btn("✅ Одобрить", f"freeze_action:approve:{lesson_id}:{page}"),
        _btn("❌ Отклонить", f"freeze_action:reject:{lesson_id}:{page}"),
    ]]
    nav_row = []
    if page > 0:
        nav_row.append(_btn("⬅️", f"admin:freezes:page:{page - 1}"))
    nav_row.append(_btn(f"Заявка {page + 1}/{total_pages}", f"admin:freezes:page:{page}"))
    if page < total_pages - 1:
        nav_row.append(_btn("➡️", f"admin:freezes:page:{page + 1}"))
    if len(nav_row) > 1:
        rows.append(nav_row)
    rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_post_registration_keyboard(
    booking_url: str = "",
    website_url: str = "",
    include_level_test: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if booking_url:
        rows.append([_url_btn("📅 Записаться на пробный урок", booking_url)])
    if website_url:
        rows.append([_url_btn("↗️ Сайт и материалы", website_url)])
    if include_level_test:
        rows.append([_btn("🧪 Пройти тест уровня", "level_test:now")])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


level_test_prompt_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("✅ Да, сейчас", "level_test:now")],
    [_btn("🕒 Да, позже", "level_test:later")],
    [_btn("🙏 Не нужно, спасибо", "level_test:no")],
])


def make_level_test_link_keyboard(url: str = "", back_callback: str = "back_to_menu") -> InlineKeyboardMarkup:
    rows = []
    if url:
        rows.append([_url_btn("🧪 Открыть тест уровня", url)])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_profile_danger_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Удалить профиль", "profile:delete_me")],
        [_btn("◀️ Назад в профиль", "profile")],
    ])


def make_self_delete_review_keyboard(back_callback: str = "profile") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("⚠️ Я понимаю последствия", "self_delete:review")],
        [_btn("◀️ Назад", back_callback)],
    ])


def make_self_delete_confirm_keyboard(back_callback: str = "profile") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Да, удалить профиль", "self_delete:confirm")],
        [_btn("◀️ Назад", back_callback)],
    ])


def make_write_to_student_keyboard(telegram_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    callback_data = f"admin:write_to_student:{telegram_id}"
    if page is not None:
        callback_data += f":{page}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("💰 Оплаты", f"admin:student_payments:{telegram_id}"),
            _btn("✉️ Написать", callback_data),
        ],
    ])


def make_admin_students_list_keyboard(
    students: list,
    page: int,
    page_size: int,
    active_filter: str = "all",
    active_sort: str = "name",
    has_query: bool = False,
) -> InlineKeyboardMarkup:
    def filter_button(text: str, callback_data: str, is_active: bool) -> InlineKeyboardButton:
        prefix = "• " if is_active else ""
        return _btn(f"{prefix}{text}", callback_data)

    rows = []
    rows.append([
        _btn("🔎 Поиск по имени", "admin:students:search"),
        _btn("🧹 Сбросить", "admin:students:reset"),
    ])
    rows.append([
        filter_button("Все", "admin:students:filter:all", active_filter == "all"),
        filter_button("Нужно внимание", "admin:students:filter:attention", active_filter == "attention"),
    ])
    rows.append([
        filter_button("0 на балансе", "admin:students:filter:zero_balance", active_filter == "zero_balance"),
        filter_button("Без урока", "admin:students:filter:no_upcoming", active_filter == "no_upcoming"),
    ])
    rows.append([
        filter_button("Имя", "admin:students:sort:name", active_sort == "name"),
        filter_button("Баланс", "admin:students:sort:balance", active_sort == "balance"),
        filter_button("Урок", "admin:students:sort:lesson", active_sort == "lesson"),
    ])
    if has_query:
        rows.append([_btn("✖️ Очистить поиск", "admin:students:search_clear")])

    start = page * page_size
    page_items = students[start:start + page_size]

    for offset, student in enumerate(page_items, start=1):
        index = start + offset
        label = f"{index}. {student['full_name']}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([
            _btn(label, f"admin:student_card:{student['telegram_id']}:{page}")
        ])

    total_pages = max(1, (len(students) + page_size - 1) // page_size)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("⬅️", f"admin:students:page:{page - 1}"))
        nav_row.append(_btn(f"Стр. {page + 1}/{total_pages}", f"admin:students:page:{page}"))
        if page < total_pages - 1:
            nav_row.append(_btn("➡️", f"admin:students:page:{page + 1}"))
        rows.append(nav_row)

    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_student_card_keyboard(
    telegram_id: int,
    page: int,
    lesson_format: str = "online",
    speech_style: str = "formal",
    lesson_duration_minutes: int = 90,
) -> InlineKeyboardMarkup:
    return make_admin_student_overview_keyboard(telegram_id, page)


def make_admin_student_overview_keyboard(telegram_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("⚡ Действия", f"admin:student_actions:{telegram_id}:{page}"),
            _btn("⚙️ Настройки", f"admin:student_settings:{telegram_id}:{page}"),
        ],
        [_btn("🛡 Опасные действия", f"admin:student_danger:{telegram_id}:{page}")],
        [_btn("◀️ К списку учеников", f"admin:students:page:{page}")],
        [_btn("◀️ К панели", "back_to_admin")],
    ])


def make_admin_student_actions_keyboard(telegram_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✉️ Написать", f"admin:write_to_student:{telegram_id}:{page}:actions"),
            _btn("💰 Оплаты", f"admin:student_payments:{telegram_id}:{page}:actions"),
        ],
        [
            _btn("➕ Урок", f"admin:quick:add_lesson:{telegram_id}:{page}:actions"),
            _btn("💳 Добавить оплату", f"admin:quick:add_payment:{telegram_id}:{page}:actions"),
        ],
        [_btn("📚 Задать ДЗ", f"admin:quick:add_homework:{telegram_id}:{page}:actions")],
        [_btn("◀️ К карточке ученика", f"admin:student_card:{telegram_id}:{page}")],
    ])


def make_admin_student_settings_keyboard(
    telegram_id: int,
    page: int,
    lesson_format: str = "online",
    speech_style: str = "formal",
    lesson_duration_minutes: int = 90,
) -> InlineKeyboardMarkup:
    is_offline = lesson_format == "offline"
    format_label = "🏠 Формат: очно" if is_offline else "💻 Формат: онлайн"
    toggle_to = "online" if is_offline else "offline"
    toggle_label = "Переключить на онлайн" if is_offline else "Переключить на очно"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"⏱ Длительность урока: {lesson_duration_minutes} мин", f"admin:student_duration:{telegram_id}:{page}")],
        [_btn(f"{format_label} · {toggle_label}", f"admin:student_format:{telegram_id}:{page}:{toggle_to}")],
        [_btn(
            f"🗣 Обращение: {speech_style_label(speech_style)} · {speech_style_toggle_label(speech_style)}",
            f"admin:student_speech_style:{telegram_id}:{page}:{'informal' if speech_style == 'formal' else 'formal'}",
        )],
        [_btn("◀️ К карточке ученика", f"admin:student_card:{telegram_id}:{page}")],
    ])


def make_admin_student_danger_keyboard(telegram_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Деактивировать", f"admin:student_deactivate_prompt:{telegram_id}:{page}")],
        [_btn("💀 Удалить навсегда", f"admin:student_delete_prompt:{telegram_id}:{page}")],
        [_btn("◀️ К карточке ученика", f"admin:student_card:{telegram_id}:{page}")],
    ])


def make_admin_parents_list_keyboard(
    parents: list,
    page: int,
    page_size: int,
    has_query: bool = False,
) -> InlineKeyboardMarkup:
    rows = [[_btn("🔎 Поиск по имени", "admin:parents:search")]]
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


def make_admin_parent_card_keyboard(telegram_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🪟 Открыть как родитель", f"admin:parent_preview_select:{telegram_id}:{page}")],
        [_btn("🛡 Опасные действия", f"admin:parent_danger:{telegram_id}:{page}")],
        [_btn("◀️ К списку родителей", f"admin:parents:page:{page}")],
    ])


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


def make_payment_delete_keyboard(student_id: int, payments: list, page: int | None = None, source: str = "card") -> InlineKeyboardMarkup:
    rows = []
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


def make_contacts_keyboard(
    booking_url: str = "",
    calendar_url: str = "",
    vk_call_url: str = "",
    google_meet_url: str = "",
    website_url: str = "",
) -> InlineKeyboardMarkup:
    rows = []
    if vk_call_url:
        rows.append([_url_btn("📞 VK Звонок", vk_call_url)])
    if google_meet_url:
        rows.append([_url_btn("📹 Google Meet (VPN)", google_meet_url)])
    if calendar_url:
        rows.append([_url_btn("📅 Открыть расписание", calendar_url)])
    if booking_url:
        rows.append([_url_btn("📝 Записаться на урок", booking_url)])
    if website_url:
        rows.append([_url_btn("↗️ Сайт и материалы", website_url)])
    rows.append([_btn("◀️ Главное меню", "back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_back_button_keyboard(label: str, callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(label, callback_data)],
    ])


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


def make_admin_student_picker_keyboard(students: list, flow: str, page: int, page_size: int) -> InlineKeyboardMarkup:
    rows = []
    start = page * page_size
    page_items = students[start:start + page_size]

    for offset, student in enumerate(page_items, start=1):
        index = start + offset
        format_icon = "🏠" if (student.get("lesson_format") or "online") == "offline" else "💻"
        balance = int(student.get("lesson_balance") or 0)
        label = f"{index}. {student['full_name']} · {format_icon} · {balance}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"admin:student_pick_select:{flow}:{student['telegram_id']}:{page}")])

    total_pages = max(1, (len(students) + page_size - 1) // page_size)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("⬅️", f"admin:student_pick:{flow}:{page - 1}"))
        nav_row.append(_btn(f"Стр. {page + 1}/{total_pages}", f"admin:student_pick:{flow}:{page}"))
        if page < total_pages - 1:
            nav_row.append(_btn("➡️", f"admin:student_pick:{flow}:{page + 1}"))
        rows.append(nav_row)

    if flow == "calendar_aliases":
        back_callback = "admin:service:monitoring"
        back_label = "◀️ К мониторингу"
    elif flow == "preview_student":
        back_callback = "admin:preview"
        back_label = "◀️ К просмотру"
    else:
        back_callback = "admin:cat:education"
        back_label = "◀️ К учебному процессу"
    rows.append([_btn(back_label, back_callback)])
    rows.append([_btn("❌ Отмена", "cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_preview_hub_keyboard(has_active_preview: bool = False) -> InlineKeyboardMarkup:
    rows = [[
        _btn("👨‍🎓 Как ученик", "admin:preview:students"),
        _btn("👨‍👩‍👧 Как родитель", "admin:preview:parents"),
    ]]
    if has_active_preview:
        rows.append([
            _btn("🪟 Открыть просмотр", "admin:preview:open"),
            _btn("🛑 Выйти", "admin:preview:stop"),
        ])
    rows.append([_btn("◀️ К панели", "admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_parent_picker_keyboard(parents: list, page: int, page_size: int) -> InlineKeyboardMarkup:
    rows = []
    start = page * page_size
    page_items = parents[start:start + page_size]

    for offset, parent in enumerate(page_items, start=1):
        index = start + offset
        linked = int(parent.get("linked_children_count") or 0)
        total = int(parent.get("children_count") or 0)
        label = f"{index}. {parent['full_name']} · {linked}/{total}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"admin:parent_preview_select:{parent['telegram_id']}:{page}")])

    total_pages = max(1, (len(parents) + page_size - 1) // page_size)
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("⬅️", f"admin:preview:parents:page:{page - 1}"))
        nav_row.append(_btn(f"Стр. {page + 1}/{total_pages}", f"admin:preview:parents:page:{page}"))
        if page < total_pages - 1:
            nav_row.append(_btn("➡️", f"admin:preview:parents:page:{page + 1}"))
        rows.append(nav_row)

    rows.append([_btn("◀️ К просмотру", "admin:preview")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Admin notes ──────────────────────────────────────────────────────────────

admin_notes_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [_btn("➕ Новая заметка", "admin:notes:add")],
    [_btn("🧹 Очистить ленту", "admin:notes:clear")],
    [_btn("◀️ К контексту", "admin:service:context")],
])


def make_homework_delete_keyboard(items: list) -> InlineKeyboardMarkup:
    rows = []
    for i, hw in enumerate(items, 1):
        deadline_str = hw["deadline"].strftime("%d.%m.%Y") if hw.get("deadline") else "—"
        label = f"📝 {i}. {hw['full_name']} · до {deadline_str}"
        if len(label) > 60:
            label = label[:58] + "…"
        rows.append([_btn(label, f"admin:homework_manage:{hw['id']}")])
    rows.append([_btn("◀️ К учебному процессу", "admin:cat:education")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_homework_manage_actions_keyboard(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✏️ Редактировать", f"hw_edit_start:{hw_id}")],
        [_btn("🗑 Удалить", f"hw_delete_confirm:{hw_id}")],
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


# ─── Lesson management ────────────────────────────────────────────────────────

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
    rows.append([_btn("◀️ К мониторингу", "admin:service:monitoring")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_calendar_alias_editor_keyboard(student_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Очистить правила", f"calendar_aliases:clear:{student_id}")],
        [_btn("◀️ К списку учеников", "admin:calendar_aliases")],
        [_btn("❌ Отмена", "cancel_fsm")],
    ])


def make_brand_tone_keyboard(current_tone: str, back_callback: str = "admin:service:context") -> InlineKeyboardMarkup:
    rows = []
    for tone, label in BRAND_TONE_LABELS.items():
        prefix = "• " if tone == current_tone else ""
        rows.append([_btn(f"{prefix}{label.capitalize()}", f"admin:brand_tone_set:{tone}")])
    rows.append([_btn("◀️ Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
