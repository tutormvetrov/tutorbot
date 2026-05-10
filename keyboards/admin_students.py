from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards._helpers import _btn, _url_btn
from utils.speech import speech_style_label, speech_style_toggle_label


# ─── Deactivate/delete confirm ────────────────────────────────────────────────

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


# ─── Freeze queue ─────────────────────────────────────────────────────────────

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


# ─── Post-registration ────────────────────────────────────────────────────────

def make_post_registration_keyboard(
    booking_url: str = "",
    website_url: str = "",
    materials_url: str = "",
    include_level_test: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if booking_url:
        rows.append([_url_btn("📅 Записаться на пробный урок", booking_url)])
    if materials_url:
        rows.append([_url_btn("📁 Учебные материалы", materials_url)])
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


# ─── Profile danger + self-delete ─────────────────────────────────────────────

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


# ─── Student list/card/overview/actions/settings/stage/danger ─────────────────

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
        _btn("🔎 Поиск: имя, ID, язык", "admin:students:search"),
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
        prefix = "🚫 " if student.get("homework_exempt") else ""
        label = f"{index}. {prefix}{student['full_name']}"
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
    homework_exempt: bool = False,
) -> InlineKeyboardMarkup:
    return make_admin_student_overview_keyboard(telegram_id, page, homework_exempt=homework_exempt)


def make_admin_student_overview_keyboard(
    telegram_id: int,
    page: int,
    homework_exempt: bool = False,
) -> InlineKeyboardMarkup:
    hw_label = "🚫 ДЗ-режим: не задаю · вернуть" if homework_exempt else "📚 ДЗ-режим: задаю · отключить"
    hw_target = "0" if homework_exempt else "1"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("⚡ Действия", f"admin:student_actions:{telegram_id}:{page}"),
            _btn("⚙️ Настройки", f"admin:student_settings:{telegram_id}:{page}"),
        ],
        [_btn(hw_label, f"admin:student_homework_exempt_card:{telegram_id}:{page}:{hw_target}")],
        [_btn("🛡 Опасные действия", f"admin:student_danger:{telegram_id}:{page}")],
        [_btn("◀️ К списку учеников", f"admin:students:page:{page}")],
        [_btn("◀️ К панели", "back_to_admin")],
    ])


def make_admin_student_actions_keyboard(
    telegram_id: int,
    page: int,
    frozen_until=None,
) -> InlineKeyboardMarkup:
    if frozen_until is None:
        freeze_button = _btn(
            "❄️ Заморозить ученика",
            f"admin:student_freeze:{telegram_id}:{page}",
        )
    else:
        # 2100-01-01 — sentinel «бессрочно»
        if frozen_until.year >= 2100:
            label = "☀️ Разморозить (бессрочно)"
        else:
            label = f"☀️ Разморозить (до {frozen_until.strftime('%d.%m')})"
        freeze_button = _btn(label, f"admin:student_unfreeze:{telegram_id}:{page}")
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
        [_btn("⚠️ Отметить прогул", f"admin:no_show:{telegram_id}:{page}")],
        [freeze_button],
        [_btn("📌 Учебный план", f"admin:study_plan:{telegram_id}:{page}:actions")],
        [_btn("📁 Учебные ссылки", f"admin:resources:student:{telegram_id}:{page}")],
        [_btn("◀️ К карточке ученика", f"admin:student_card:{telegram_id}:{page}")],
    ])


def make_admin_student_freeze_period_keyboard(
    telegram_id: int, page: int
) -> InlineKeyboardMarkup:
    base = f"admin:student_freeze_set:{telegram_id}:{page}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("На неделю", f"{base}:7d")],
        [_btn("На 2 недели", f"{base}:14d")],
        [_btn("На месяц", f"{base}:30d")],
        [_btn("На 3 месяца", f"{base}:90d")],
        [_btn("Бессрочно", f"{base}:forever")],
        [_btn("◀️ Отмена", f"admin:student_actions:{telegram_id}:{page}")],
    ])


def make_admin_student_freeze_lessons_prompt_keyboard(
    telegram_id: int, page: int, period: str, lessons_count: int
) -> InlineKeyboardMarkup:
    """Подтверждение: переводить ли N запланированных уроков в `frozen`."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(
            f"✅ Да, перевести {lessons_count} уроков",
            f"admin:student_freeze_apply:{telegram_id}:{page}:{period}:yes",
        )],
        [_btn(
            "Нет, оставить как есть",
            f"admin:student_freeze_apply:{telegram_id}:{page}:{period}:no",
        )],
        [_btn("◀️ Отмена", f"admin:student_actions:{telegram_id}:{page}")],
    ])


def make_admin_student_settings_keyboard(
    telegram_id: int,
    page: int,
    lesson_format: str = "online",
    speech_style: str = "formal",
    lesson_duration_minutes: int = 90,
    student_type: str = "adult",
    preferred_name: str | None = None,
    homework_exempt: bool = False,
) -> InlineKeyboardMarkup:
    is_offline = lesson_format == "offline"
    format_label = "🏠 Формат: очно" if is_offline else "💻 Формат: онлайн"
    toggle_to = "online" if is_offline else "offline"
    toggle_label = "Переключить на онлайн" if is_offline else "Переключить на очно"
    type_label = "🎒 Тип: Школьник" if student_type == "schoolchild" else "🎓 Тип: Взрослый"
    name_for_label = (preferred_name or "—").strip() or "—"
    if len(name_for_label) > 24:
        name_for_label = name_for_label[:23] + "…"
    hw_exempt_label = "🚫 ДЗ: не задаю" if homework_exempt else "📚 ДЗ: задаю"
    hw_exempt_target = "0" if homework_exempt else "1"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"✏️ Имя для обращения: {name_for_label}", f"admin:student_preferred_name:{telegram_id}:{page}")],
        [_btn("💳 Тариф", f"admin:student_tariff:{telegram_id}:{page}")],
        [_btn(f"⏱ Длительность урока: {lesson_duration_minutes} мин", f"admin:student_duration:{telegram_id}:{page}")],
        [_btn(f"{format_label} · {toggle_label}", f"admin:student_format:{telegram_id}:{page}:{toggle_to}")],
        [_btn(
            f"🗣 Обращение: {speech_style_label(speech_style)} · {speech_style_toggle_label(speech_style)}",
            f"admin:student_speech_style:{telegram_id}:{page}:{'informal' if speech_style == 'formal' else 'formal'}",
        )],
        [_btn(type_label, f"admin:student_type_toggle:{telegram_id}:{page}")],
        [_btn("📊 Стадия ученика", f"admin:student_stage:{telegram_id}:{page}")],
        [_btn(hw_exempt_label, f"admin:student_homework_exempt:{telegram_id}:{page}:{hw_exempt_target}")],
        [_btn("◀️ К карточке ученика", f"admin:student_card:{telegram_id}:{page}")],
    ])


def make_admin_student_stage_keyboard(
    telegram_id: int,
    page: int,
    current_stage: str,
    is_overridden: bool,
) -> InlineKeyboardMarkup:
    from utils.ui_text import STUDENT_STAGE_ICONS, STUDENT_STAGE_LABELS

    rows = []
    for stage_key in ("new", "regular", "veteran"):
        icon = STUDENT_STAGE_ICONS[stage_key]
        label = STUDENT_STAGE_LABELS[stage_key]
        marker = " ✓" if stage_key == current_stage else ""
        rows.append([_btn(
            f"{icon} {label}{marker}",
            f"admin:student_stage_set:{telegram_id}:{page}:{stage_key}",
        )])
    if is_overridden:
        rows.append([_btn("🔄 Вернуть авто-определение", f"admin:student_stage_set:{telegram_id}:{page}:auto")])
    rows.append([_btn("◀️ К настройкам", f"admin:student_settings:{telegram_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_student_danger_keyboard(telegram_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🗑 Деактивировать", f"admin:student_deactivate_prompt:{telegram_id}:{page}")],
        [_btn("💀 Удалить навсегда", f"admin:student_delete_prompt:{telegram_id}:{page}")],
        [_btn("◀️ К карточке ученика", f"admin:student_card:{telegram_id}:{page}")],
    ])


# ─── Pairs ────────────────────────────────────────────────────────────────────

def make_admin_pairs_list_keyboard(pairs: list) -> InlineKeyboardMarkup:
    rows = [[_btn("➕ Создать пару", "admin:pairs:add")]]
    for pair in pairs:
        label = f"👥 {pair.get('title') or pair.get('primary_student_name') or 'Пара'}"
        if len(label) > 64:
            label = label[:62] + "…"
        rows.append([_btn(label, f"admin:pair:{pair['id']}")])
    rows.append([_btn("◀️ К разделу «Ученики»", "admin:cat:students")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_pair_primary_keyboard(students: list) -> InlineKeyboardMarkup:
    rows = []
    for student in students:
        label = f"{student['full_name']} · {student['telegram_id']}"
        if len(label) > 64:
            label = label[:62] + "…"
        rows.append([_btn(label, f"admin:pairs:add_primary:{student['telegram_id']}")])
    rows.append([_btn("◀️ К парам", "admin:pairs")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_pair_card_keyboard(pair: dict) -> InlineKeyboardMarkup:
    primary_student_id = int(pair["primary_student_id"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn("✉️ Написать", f"admin:write_to_student:{primary_student_id}:0:card"),
            _btn("💰 Оплаты", f"admin:student_payments:{primary_student_id}:0:card"),
        ],
        [
            _btn("➕ Урок", f"admin:quick:add_lesson:{primary_student_id}:0:card"),
            _btn("📚 Задать ДЗ", f"admin:quick:add_homework:{primary_student_id}:0:card"),
        ],
        [_btn("🔗 Ссылка для второго участника", f"admin:pair_invite:{pair['id']}")],
        [_btn("📌 Учебный план", f"admin:study_plan:{primary_student_id}:0:card")],
        [_btn("👤 Основной профиль", f"admin:student_card:{primary_student_id}:0")],
        [_btn("◀️ К парам", "admin:pairs")],
    ])


def make_admin_pair_notification_keyboard(pair_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🔗 Ссылка для второго участника", f"admin:pair_invite:{pair_id}")],
        [_btn("👥 Открыть пару", f"admin:pair:{pair_id}")],
    ])


# ─── Study plan ───────────────────────────────────────────────────────────────

def make_study_plan_keyboard(plan: dict | None, checklist_items: list, *, parent_link_id: int | None = None) -> InlineKeyboardMarkup:
    prefix = f"parent:child:{parent_link_id}:study_plan" if parent_link_id is not None else "study_plan"
    rows = []
    if plan:
        rows.append([_btn("📄 Открыть PDF-план", f"{prefix}:file:{plan['id']}")])
    for item in checklist_items:
        mark = "✅" if item.get("status") == "done" else "☐"
        label = f"{mark} {item.get('title') or 'Пункт'}"
        if len(label) > 64:
            label = label[:62] + "…"
        callback = f"study_plan:toggle:{item['id']}" if parent_link_id is None else prefix
        rows.append([_btn(label, callback)])
    rows.append([_btn("📚 Домашние задания", "homework" if parent_link_id is None else f"parent:child:{parent_link_id}:homework:active")])
    rows.append([_btn("◀️ Главное меню", "back_to_menu" if parent_link_id is None else f"parent:child:{parent_link_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_study_plan_open_keyboard(parent_link_id: int | None = None) -> InlineKeyboardMarkup:
    callback = "study_plan" if parent_link_id is None else f"parent:child:{parent_link_id}:study_plan"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📌 Открыть учебный план", callback)],
    ])


def make_admin_study_plan_keyboard(student_id: int, page: int, source: str, has_plan: bool = False) -> InlineKeyboardMarkup:
    rows = [[_btn("📄 Загрузить PDF-план", f"admin:study_plan_upload:{student_id}:{page}:{source}")]]
    if has_plan:
        rows.append([_btn("➕ Пункт в чек-лист", f"admin:study_plan_item:{student_id}:{page}:{source}")])
    rows.append([_btn("◀️ К карточке ученика", f"admin:student_card:{student_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_admin_study_plan_preview_keyboard(can_publish: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_publish:
        rows.append([_btn("✅ Опубликовать", "admin:study_plan_publish")])
    rows.append([_btn("✏️ Править выжимку", "admin:study_plan_edit_summary")])
    rows.append([_btn("🔁 Загрузить другой PDF", "admin:study_plan_upload_again")])
    rows.append([_btn("❌ Отмена", "cancel_fsm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Tariffs ──────────────────────────────────────────────────────────────────

def make_pricing_rates_keyboard(rates: list) -> InlineKeyboardMarkup:
    rows = [[_btn("➕ Добавить/обновить тариф", "admin:pricing:add")]]
    for rate in rates:
        amount = int(rate.get("amount") or 0)
        label = rate.get("label") or ""
        label_part = f"{label} · " if label else ""
        rate_id = rate.get("id") or 0
        rows.append([
            _btn(
                f"{label_part}{rate['group_size']} уч. · {rate['duration_minutes']} мин · {amount} {rate.get('currency') or 'RUB'}",
                f"admin:pricing:delete:{rate_id}",
            )
        ])
    rows.append([_btn("◀️ К финансам", "admin:finance")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_tariff_picker_keyboard(
    student_id: int,
    page: int,
    rates: list,
    current_rate_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Inline keyboard for assigning a tariff to a student."""
    rows = []
    for rate in rates:
        amount = int(rate.get("amount") or 0)
        label = rate.get("label") or f"{rate['group_size']} уч. · {rate['duration_minutes']} мин"
        marker = " ✓" if rate.get("id") == current_rate_id else ""
        rows.append([_btn(
            f"{label} · {amount} {rate.get('currency') or 'RUB'}{marker}",
            f"admin:assign_tariff:{student_id}:{rate['id']}:{page}",
        )])
    if current_rate_id:
        rows.append([_btn("✖️ Снять тариф", f"admin:assign_tariff:{student_id}:0:{page}")])
    rows.append([_btn("◀️ К настройкам", f"admin:student_settings:{student_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Student picker/preview hub/parent picker ─────────────────────────────────

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
        back_callback = "admin:cat:service"
        back_label = "◀️ К сервису"
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
