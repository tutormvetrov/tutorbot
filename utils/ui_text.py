from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta

from aiogram import html

from utils.brand import (
    brand_tone_description,
    brand_tone_label,
    choose_tone_variant,
    get_brand_tone,
)
from utils.homework_delivery import delivery_badge
from utils.homework_materials import build_next_homework_hint, material_progress_label
from utils.homework_text import homework_body_html, homework_preview_text
from utils.speech import choose_form, speech_style_label
from utils.time import business_today


MAIN_MENU_TEXT = "📍 <b>Главное меню</b>\n\nВыберите, что нужно сейчас."
ACTION_CANCELLED_TEXT = "❌ Действие отменено."
REGISTRATION_REQUIRED_TEXT = "⚠️ Сначала зарегистрируйтесь через /start"
DEACTIVATED_ACCOUNT_TEXT = "⛔️ Ваш аккаунт деактивирован. Обратитесь к преподавателю."
BLOCKED_ACCOUNT_TEXT = "🚫 Доступ к боту заблокирован. Если это ошибка, обратитесь к преподавателю."
BLOCKED_ACCOUNT_ALERT = "Доступ к боту заблокирован."

ADMIN_HOME_TEXT = (
    "🛠 <b>Панель администратора</b>\n\n"
    "Сверху — живая сводка по боту. Ниже — четыре рабочих раздела."
)
ADMIN_STUDENTS_CATEGORY_TEXT = "👥 <b>Ученики</b>"
ADMIN_EDUCATION_CATEGORY_TEXT = "📚 <b>Учебный процесс</b>"
ADMIN_COMMUNICATION_CATEGORY_TEXT = (
    "📢 <b>Коммуникации</b>\n\n"
    "Рассылки, ответы ученикам и служебные сообщения."
)
ADMIN_SERVICE_CATEGORY_TEXT = "⚙️ <b>Сервис</b>"
ADMIN_SERVICE_MONITORING_TEXT = "📊 <b>Мониторинг</b>"
ADMIN_SERVICE_CONTEXT_TEXT = "🧠 <b>Контекст и проект</b>"
ADMIN_SYNC_IN_PROGRESS_TEXT = "🔄 Синхронизирую Google Calendar..."
ADMIN_SYNC_ERROR_HINT = (
    "Проверьте путь в <b>GOOGLE_CREDENTIALS_FILE</b> "
    "и корректность <b>GOOGLE_CALENDAR_ID</b>."
)

ADMIN_NO_REGISTERED_STUDENTS_TEXT = "⚠️ Нет зарегистрированных учеников."
ADMIN_NO_ACTIVE_STUDENTS_TEXT = "👥 Нет активных учеников."
ADMIN_STUDENTS_EMPTY_TEXT = "👥 <b>Список учеников</b>\n\nУчеников пока нет."
ADMIN_PARENTS_EMPTY_TEXT = "👨‍👩‍👧 <b>Список родителей</b>\n\nРодителей пока нет."
ADMIN_LESSON_FORMATS_EMPTY_TEXT = "🏫 <b>Формат занятий</b>\n\nСейчас нет активных учеников, для которых можно переключить формат."
ADMIN_SPEECH_STYLES_EMPTY_TEXT = "🗣 <b>Обращение с учениками</b>\n\nСейчас нет активных учеников, для которых можно переключить обращение."
ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT = (
    "📢 <b>Рассылка пока недоступна</b>\n\n"
    "Сейчас нет активных учеников, которым можно отправить сообщение."
)

ADMIN_ADD_LESSON_START_TEXT = "➕ <b>Добавить занятие</b>\n\nВыберите ученика, для которого хотите поставить урок."
ADMIN_ADD_LESSON_PROMPT_TEXT = (
    "📅 Введите дату и время занятия в формате:\n"
    "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
    "Например: <code>15.06.2025 14:00</code>"
)
ADMIN_ADD_LESSON_INVALID_TEXT = (
    "⚠️ Пока не получилось распознать дату. Введите её так:\n<code>15.06.2025 14:00</code>"
)
ADMIN_ADD_PAYMENT_START_TEXT = "💳 <b>Добавить оплату</b>\n\nВыберите ученика, чтобы зафиксировать оплату."
ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT = (
    "💰 Введите сумму оплаты в рублях.\n\nНапример: <code>3000</code>"
)
ADMIN_ADD_PAYMENT_AMOUNT_INVALID_TEXT = (
    "⚠️ Нужна корректная сумма. Например: <code>3000</code>"
)
ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT = (
    "🔢 Сколько уроков оплачено?\n\nНапример: <code>1</code>"
)
ADMIN_ADD_PAYMENT_COUNT_INVALID_TEXT = (
    "⚠️ Нужна целая положительная цифра. Например: <code>1</code>"
)
ADMIN_ADD_HOMEWORK_START_TEXT = "📚 <b>Задать домашнее задание</b>\n\nВыберите ученика."
ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT = (
    "📝 Отправьте <b>текст домашнего задания</b> или прикрепите <b>PDF/DOCX</b>.\n\n"
    "Можно добавить подпись, ссылки и форматирование."
)
ADMIN_ADD_HOMEWORK_EMPTY_TEXT = "⚠️ Отправьте текст задания или прикрепите PDF/DOCX."
ADMIN_ADD_HOMEWORK_DEADLINE_PROMPT_TEXT = (
    "📅 Введите дедлайн в формате <code>ДД.ММ.ГГГГ</code>.\n\n"
    "Подойдут варианты: <code>05.04.2026</code>, <code>05/04/2026</code> или <code>05\\04\\2026</code>"
)
ADMIN_ADD_HOMEWORK_DEADLINE_INVALID_TEXT = (
    "⚠️ Не удалось распознать дату. Введите её так: "
    "<code>05.04.2026</code>, <code>05/04/2026</code> или <code>05\\04\\2026</code>"
)
ADMIN_BROADCAST_START_TEXT = (
    "📢 <b>Рассылка ученикам</b>\n\n"
    "Можно выбрать готовый шаблон или отправить своё сообщение.\n"
    "Перед отправкой бот покажет точный предпросмотр."
)
ADMIN_BROADCAST_ENTER_TEXT = (
    "✏️ Введите текст сообщения для рассылки.\n\n"
    "Можно использовать форматирование и ссылки. Перед отправкой вы ещё увидите предпросмотр."
)
ADMIN_BROADCAST_EDIT_TEXT = (
    "✏️ Введите обновлённый текст сообщения.\n\n"
    "После этого снова покажу предпросмотр."
)
ADMIN_HEALTH_NO_ERRORS_TEXT = "✅ В последних журналах ошибок не найдено."

LESSON_FORMAT_LABELS = {
    "online": "онлайн",
    "offline": "очно",
}
LESSON_FORMAT_ICONS = {
    "online": "💻",
    "offline": "🏠",
}


def format_date(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    return value.strftime("%d.%m.%Y")


def format_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def format_short_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m %H:%M") if value else "—"


def _add_calendar_month(value: date) -> date:
    month = value.month + 1
    year = value.year
    if month > 12:
        month = 1
        year += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


STUDENT_STAGES = ("new", "regular", "veteran")

STUDENT_STAGE_LABELS = {
    "new": "Новый",
    "regular": "Основной",
    "veteran": "Давний",
}

STUDENT_STAGE_ICONS = {
    "new": "🆕",
    "regular": "📗",
    "veteran": "🏅",
}


def compute_student_stage(
    first_lesson_date: datetime | None,
    override: str | None = None,
    today: date | None = None,
) -> str:
    if override and override in STUDENT_STAGES:
        return override
    if not first_lesson_date:
        return "new"
    today = today or business_today()
    first_date = first_lesson_date.date() if isinstance(first_lesson_date, datetime) else first_lesson_date
    months_elapsed = (today.year - first_date.year) * 12 + (today.month - first_date.month)
    if today.day < first_date.day:
        months_elapsed -= 1
    if months_elapsed >= 5:
        return "veteran"
    if months_elapsed >= 1:
        return "regular"
    return "new"


def student_stage_label(stage: str) -> str:
    return STUDENT_STAGE_LABELS.get(stage, STUDENT_STAGE_LABELS["new"])


def student_stage_badge(
    first_lesson_date: datetime | None,
    override: str | None = None,
    today: date | None = None,
) -> str:
    stage = compute_student_stage(first_lesson_date, override=override, today=today)
    icon = STUDENT_STAGE_ICONS.get(stage, "🆕")
    label = student_stage_label(stage)
    return f"{icon} {label}"


def student_freshness_label(first_lesson_date: datetime | None, today: date | None = None) -> str:
    stage = compute_student_stage(first_lesson_date, today=today)
    return "новый" if stage == "new" else "старый"


def student_freshness_badge(first_lesson_date: datetime | None, today: date | None = None) -> str:
    return student_stage_badge(first_lesson_date, today=today)


def lesson_balance_label(balance: int | None) -> str:
    amount = int(balance or 0)
    remainder_ten = amount % 10
    remainder_hundred = amount % 100
    if 11 <= remainder_hundred <= 14:
        suffix = "уроков"
    elif remainder_ten == 1:
        suffix = "урок"
    elif remainder_ten in {2, 3, 4}:
        suffix = "урока"
    else:
        suffix = "уроков"
    return f"{amount} {suffix}"


def lesson_format_label(value: str | None) -> str:
    return LESSON_FORMAT_LABELS.get(value or "online", LESSON_FORMAT_LABELS["online"])


def lesson_format_icon(value: str | None) -> str:
    return LESSON_FORMAT_ICONS.get(value or "online", LESSON_FORMAT_ICONS["online"])


def lesson_duration_label(value: int | None) -> str:
    try:
        minutes = int(value or 90)
    except (TypeError, ValueError):
        minutes = 90
    return f"{minutes} мин"


def _item_value(item, key: str, default=None):
    if item is None:
        return default
    getter = getattr(item, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return item[key]
    except Exception:
        return default


def reminder_status_label(reminders: str | None) -> str:
    reminders = reminders or "enabled"
    if reminders == "disabled":
        return "отключены"
    if reminders.startswith("paused_until:"):
        return f"на паузе до {reminders.split(':', 1)[1]}"
    return "включены"


def reminder_status_hint(reminders: str | None) -> str:
    reminders = reminders or "enabled"
    if reminders == "disabled":
        return "Напоминания отключены."
    if reminders.startswith("paused_until:"):
        until = reminders.split(":", 1)[1]
        return f"Пауза действует до <b>{html.quote(until)}</b>. После этого напоминания снова включатся автоматически."
    return (
        "Онлайн-уроки: напоминание за <b>10 минут</b>.\n"
        "Очные уроки: напоминание за <b>1 час</b>."
    )


def next_lesson_label(lessons: list) -> str:
    lesson_date = None
    for lesson in lessons or []:
        if lesson.get("lesson_date"):
            lesson_date = lesson["lesson_date"]
            break
    if not lesson_date:
        return "не назначено"
    return format_datetime(lesson_date)


def pair_title_label(pair: dict | None) -> str:
    if not pair:
        return ""
    title = (pair.get("title") or "").strip()
    if title:
        return title
    member_names = [str(name).strip() for name in pair.get("member_names") or [] if str(name).strip()]
    return " + ".join(member_names)


def build_student_home_text(
    user,
    balance: int,
    active_homework_count: int,
    next_lesson: datetime | None = None,
    pair: dict | None = None,
    journey_progress: dict | None = None,
) -> str:
    full_name = html.quote(user.get("full_name") or "—")
    next_lesson_text = format_datetime(next_lesson) if next_lesson else "не назначен"

    lines = [
        "📍 <b>Главное меню</b>",
        "",
        f"<b>{full_name}</b>",
    ]
    pair_label = pair_title_label(pair)
    if pair_label:
        lines.extend([
            f"👥 Пара: <b>{html.quote(pair_label)}</b>",
            "Общий темп, общий баланс и одно домашнее задание на двоих.",
        ])
        shared_goal = (pair or {}).get("shared_goal_text") if isinstance(pair, dict) else None
        if shared_goal:
            lines.append(f"🎯 Наша цель: <b>{html.quote(str(shared_goal))}</b>")
        else:
            lines.append("🎯 Общая цель ещё не задана — нажмите «🎯 Наша цель», чтобы поставить.")
    lines.extend([
        f"📅 Ближайший урок: <b>{html.quote(next_lesson_text)}</b>",
        f"📚 Активные ДЗ: <b>{int(active_homework_count or 0)}</b>",
        f"🎓 Баланс: <b>{lesson_balance_label(balance)}</b>",
        "",
    ])

    if journey_progress and _should_show_journey_progress(journey_progress):
        lines.append(build_journey_progress_text(journey_progress))
        lines.append("")

    if not next_lesson:
        lines.append("Нет запланированных уроков.")
    return "\n".join(lines)


def _should_show_journey_progress(progress: dict) -> bool:
    """Show progress only during the first 14 days and not after completion."""
    if not progress:
        return False
    if progress.get("completed"):
        return False
    registered_at = progress.get("registered_at")
    if registered_at is None:
        return False
    try:
        age = datetime.now() - registered_at  # naive vs naive
    except TypeError:
        return False
    return age <= timedelta(days=14)


def build_schedule_text(lessons: list, lesson_format: str | None = None) -> str:
    if not lessons:
        return (
            "📅 <b>Расписание</b>\n\n"
            "Ближайших занятий пока нет.\n\n"
            "Как только преподаватель добавит урок, он появится здесь."
        )

    next_lesson = None
    next_lesson_format = lesson_format
    lines = []
    for lesson in lessons:
        lesson_date = lesson.get("lesson_date")
        item_format = lesson.get("lesson_format") or lesson_format or "online"
        if lesson_date and next_lesson is None:
            next_lesson = lesson_date
            next_lesson_format = item_format
        lines.append(
            f"• <b>{format_datetime(lesson_date)}</b> · "
            f"{lesson_format_icon(item_format)} {lesson_format_label(item_format)}"
        )

    title = "📅 <b>Расписание</b>"
    if next_lesson:
        title += f"\n\nБлижайший урок: <b>{format_datetime(next_lesson)}</b>"
    if next_lesson_format:
        title += (
            f"\nФормат: <b>{lesson_format_label(next_lesson_format)}</b>"
        )
    title += f"\nВсего в расписании: <b>{len(lessons)}</b>"
    return title + "\n\n" + "\n".join(lines)


def build_profile_text(
    user,
    balance: int,
    lessons: list | None = None,
    reminders: str | None = None,
    children: list[str] | None = None,
    next_lesson: datetime | None = None,
    pair: dict | None = None,
) -> str:
    role_labels = {
        "student": "Ученик",
        "parent": "Родитель",
        "teacher_admin": "Преподаватель",
    }
    reg_date = format_date(user.get("registration_date"))
    full_name = html.quote(user.get("full_name") or "—")
    role_label = role_labels.get(user.get("role"), user.get("role") or "—")

    lines = [
        "👤 <b>Профиль</b>",
        "",
        f"<b>{full_name}</b>",
        f"🎭 Роль: <b>{role_label}</b>",
        f"📅 В системе с: <b>{reg_date}</b>",
    ]

    if user.get("role") == "student":
        lesson_label = format_datetime(next_lesson) if next_lesson else next_lesson_label(lessons or [])
        lines.extend([
            f"🎓 Остаток уроков: <b>{lesson_balance_label(balance)}</b>",
            f"📅 Ближайшее занятие: <b>{html.quote(lesson_label)}</b>",
            f"🔔 Напоминания: <b>{html.quote(reminder_status_label(reminders))}</b>",
            f"🏫 Формат занятий: <b>{lesson_format_label(user.get('lesson_format'))}</b>",
        ])
        pair_label = pair_title_label(pair)
        if pair_label:
            lines.extend([
                "",
                "👥 Формат: <b>занятия в паре</b>",
                f"Пара: <b>{html.quote(pair_label)}</b>",
                "Баланс, темп и домашние задания ведутся общими.",
            ])
    elif user.get("role") == "parent":
        lines.append("👨‍👩‍👧 <b>Дети в системе:</b>")
        if children:
            for child in children:
                if isinstance(child, dict):
                    status = child.get("link_status")
                    status_label = "✅ Привязан" if status == "linked" else "⏳ Ждём совпадение по имени"
                    lines.append(f"• {html.quote(child.get('child_label') or '—')} — {status_label}")
                else:
                    lines.append(f"• {html.quote(child)}")
        else:
            lines.append("• Пока нет привязанных учеников.")

    return "\n".join(lines)


def build_payment_text(balance: int, payments: list, transactions: list | None = None) -> str:
    if transactions is not None:
        return build_transaction_history_text(balance, transactions)
    lines = [
        "💰 <b>Оплата</b>",
        "",
        f"Сейчас на балансе: <b>{lesson_balance_label(balance)}</b>",
    ]

    if not payments:
        lines.extend([
            "",
            "Оплат в истории пока нет.",
            "Когда преподаватель внесёт оплату, она появится здесь.",
        ])
        return "\n".join(lines)

    lines.extend([
        "",
        "",
        "",
        "💳 <b>История оплат</b>",
    ])
    for index, payment in enumerate(payments, 1):
        date_str = format_date(payment.get("payment_date"))
        lines.extend([
            "",
            f"{index}. <b>{int(payment['amount'])} ₽</b> · {payment['lessons_count']} ур.",
            f"   📅 {date_str}",
        ])
    return "\n".join(lines)


def money_label(amount, currency: str | None = "RUB") -> str:
    try:
        numeric = float(amount or 0)
    except (TypeError, ValueError):
        numeric = 0
    if numeric.is_integer():
        value = str(int(numeric))
    else:
        value = f"{numeric:.2f}".rstrip("0").rstrip(".")
    currency = (currency or "RUB").upper()
    suffix = "₽" if currency == "RUB" else currency
    return f"{value} {suffix}"


def build_study_plan_text(
    user,
    plan,
    lesson,
    homework: list,
    checklist_items: list,
    pair: dict | None = None,
) -> str:
    full_name = html.quote(user.get("full_name") or "—")
    done_count = sum(1 for item in checklist_items if item.get("status") == "done")
    total_count = len(checklist_items)
    plan_summary = (plan or {}).get("summary") or ""
    pair_label = pair_title_label(pair)

    lines = [
        "📌 <b>Учебный план</b>",
        "",
        f"<b>{full_name}</b>",
    ]
    if pair_label:
        lines.append(f"👥 Пара: <b>{html.quote(pair_label)}</b>")

    lines.extend([
        f"📅 Ближайший урок: <b>{html.quote(format_datetime(lesson.get('lesson_date')) if lesson else 'не назначен')}</b>",
        f"📚 Активные ДЗ: <b>{len(homework or [])}</b>",
        f"✅ Подготовка: <b>{done_count}/{total_count}</b>",
        "",
    ])

    if plan_summary:
        lines.extend([
            "🧭 <b>Фокус трёхмесячного плана</b>",
            html.quote(plan_summary),
            "",
        ])
    else:
        lines.extend([
            "🧭 <b>Фокус трёхмесячного плана</b>",
            "План пока не опубликован. Когда преподаватель загрузит PDF, он появится здесь.",
            "",
        ])

    if checklist_items:
        lines.append("🧩 <b>До следующего урока</b>")
        for item in checklist_items:
            mark = "✅" if item.get("status") == "done" else "☐"
            lines.append(f"{mark} {html.quote(item.get('title') or 'Пункт')}")
    elif lesson:
        lines.append("🧩 Чек-лист появится здесь автоматически.")
    else:
        lines.append("🧩 Чек-лист появится, когда будет назначен следующий урок.")

    return "\n".join(lines)


def build_admin_study_plan_text(student_name: str, active_plan, history: list) -> str:
    lines = [
        "📌 <b>Учебный план ученика</b>",
        "",
        f"👤 Ученик: <b>{html.quote(student_name)}</b>",
    ]
    if active_plan:
        lines.extend([
            "",
            "✅ <b>Активный план</b>",
            f"📄 {html.quote(active_plan.get('file_name') or 'PDF-план')}",
            f"📅 Опубликован: <b>{format_datetime(active_plan.get('published_at'))}</b>",
            "",
            html.quote(active_plan.get("summary") or "Выжимка пока пустая."),
        ])
    else:
        lines.extend([
            "",
            "Активного плана пока нет.",
            "Загрузите PDF, проверьте распознанный текст и опубликуйте выжимку для ученика.",
        ])
    if history:
        lines.extend(["", f"🗂 В истории: <b>{len(history)}</b>"])
    return "\n".join(lines)


def build_admin_study_plan_preview_text(parsed: dict, summary: str) -> str:
    warnings = parsed.get("warnings") or []
    parsed_text = parsed.get("text") or ""
    preview = parsed_text[:1600].rstrip()
    if len(parsed_text) > len(preview):
        preview += "\n…"

    lines = [
        "📄 <b>Предпросмотр PDF-плана</b>",
        "",
        f"Файл: <b>{html.quote(parsed.get('file_name') or 'PDF-план')}</b>",
        f"Страниц: <b>{int(parsed.get('pages_count') or 0)}</b>",
        f"Таблиц найдено: <b>{int(parsed.get('tables_count') or 0)}</b>",
        f"Статус парсинга: <b>{html.quote(parsed.get('status') or 'ok')}</b>",
    ]
    if warnings:
        lines.extend(["", "⚠️ <b>Предупреждения</b>"])
        lines.extend(f"• {html.quote(str(item))}" for item in warnings[:4])

    lines.extend([
        "",
        "🧭 <b>Выжимка для ученика</b>",
        html.quote(summary or "Выжимка пустая. Отредактируйте её перед публикацией."),
        "",
        "📖 <b>Фрагмент распознанного текста</b>",
        html.quote(preview or "Текст не извлечён."),
    ])
    return "\n".join(lines)


def build_weekly_study_plan_text(row, *, for_parent: bool = False) -> str:
    name = row.get("student_name") or row.get("full_name") or "ученик"
    done = int(row.get("checklist_done") or 0)
    total = int(row.get("checklist_total") or 0)
    summary = row.get("summary") or "Откройте план, чтобы посмотреть фокус ближайшего этапа."
    title = "👨‍👩‍👧 <b>Учебный план на неделю</b>" if for_parent else "📌 <b>Учебный план на неделю</b>"
    lines = [
        title,
        "",
        f"👤 {html.quote(name)}",
        f"📅 Ближайший урок: <b>{html.quote(format_datetime(row.get('next_lesson_date')) if row.get('next_lesson_date') else 'не назначен')}</b>",
        f"📚 Активные ДЗ: <b>{int(row.get('active_homework_count') or 0)}</b>",
        f"✅ Подготовка: <b>{done}/{total}</b>",
        "",
        "🧭 <b>Фокус</b>",
        html.quote(summary),
    ]
    return "\n".join(lines)


def build_pricing_rates_text(rates: list) -> str:
    lines = [
        "💳 <b>Тарифы занятий</b>",
        "",
        "Цена считается за занятие целиком, не за одного участника.",
    ]
    if not rates:
        lines.extend(["", "Тарифов пока нет. Добавьте первый тариф ниже."])
        return "\n".join(lines)
    lines.append("")
    for rate in rates:
        label = rate.get("label") or ""
        label_part = f"<b>{html.quote(label)}</b> · " if label else ""
        lines.append(
            f"• {label_part}"
            f"{int(rate['group_size'])} уч. · "
            f"{int(rate['duration_minutes'])} мин · "
            f"<b>{html.quote(money_label(rate['amount'], rate.get('currency')))}</b>"
        )
    return "\n".join(lines)


def format_tariff_display(rate) -> str:
    """Format a pricing rate for display on student card."""
    if not rate:
        return "не назначен"
    label = rate.get("label") or ""
    amount = int(rate["amount"]) if float(rate["amount"]) == int(float(rate["amount"])) else rate["amount"]
    currency = rate.get("currency") or "RUB"
    duration = int(rate.get("duration_minutes") or 90)
    if label:
        return f"{label} ({amount} {currency} / {duration} мин)"
    return f"{amount} {currency} / {duration} мин"


def build_tariff_picker_text(student_name: str, rates: list, current_rate_id: int | None) -> str:
    """Build text for the tariff assignment picker screen."""
    lines = [f"💳 <b>Тариф для {student_name}</b>"]
    current_label = "не назначен"
    if current_rate_id:
        for rate in rates:
            if rate.get("id") == current_rate_id:
                current_label = format_tariff_display(rate)
                break
    lines.append(f"\nТекущий: <b>{html.quote(current_label)}</b>")
    if rates:
        lines.append("\nВыберите тариф из списка:")
    else:
        lines.append("\nТарифов пока нет. Добавьте через раздел «Тарифы» в настройках.")
    return "\n".join(lines)


def build_materials_text(
    resources: list | None = None,
    *,
    website_url: str = "",
) -> str:
    """Build the «Материалы» screen text.

    `resources` — list of dicts (see `list_student_resources`); empty/None falls
    back to a soft "not configured" message that points to the website if any.
    """
    from html import escape

    from utils.resource_provider import provider_emoji, provider_label

    items = list(resources or [])
    lines = ["📁 <b>Учебные материалы</b>"]

    if not items:
        if website_url:
            lines.extend([
                "",
                "Материалы и учебники собраны на сайте преподавателя.",
                "Откройте сайт по кнопке ниже — там же тест уровня и информация о занятиях.",
            ])
        else:
            lines.extend([
                "",
                "Ссылка на учебные материалы пока не подключена.",
                "Напишите преподавателю — он пришлёт нужные файлы напрямую.",
            ])
        return "\n".join(lines)

    # If exactly one resource — flat layout, no group headers.
    if len(items) == 1:
        r = items[0]
        emoji = provider_emoji(r.get("provider") or "other")
        plabel = provider_label(r.get("provider") or "other")
        lines.extend([
            "",
            f"{emoji} <b>{escape(r.get('label') or plabel)}</b> · {plabel}",
            "",
        ])
        return "\n".join(lines)

    primary = next((r for r in items if r.get("is_primary")), None)
    globals_ = [r for r in items if r.get("student_id") is None and r is not primary]
    personal = [r for r in items if r.get("student_id") is not None and r is not primary]

    def _fmt(r: dict) -> str:
        emoji = provider_emoji(r.get("provider") or "other")
        plabel = provider_label(r.get("provider") or "other")
        label = escape(r.get("label") or plabel)
        return f"   {emoji} <b>{label}</b> · {plabel}"

    if primary:
        emoji = provider_emoji(primary.get("provider") or "other")
        plabel = provider_label(primary.get("provider") or "other")
        label = escape(primary.get("label") or plabel)
        lines.extend([
            "",
            "⭐ <b>Основное</b>",
            f"   {emoji} <b>{label}</b> · {plabel}",
        ])
    if globals_:
        lines.extend(["", "🌍 <b>Общие</b>"])
        lines.extend(_fmt(r) for r in globals_)
    if personal:
        lines.extend(["", "👤 <b>Дополнительно для вас</b>"])
        lines.extend(_fmt(r) for r in personal)
    return "\n".join(lines)


def build_admin_student_resources_text(student_name: str, resources: list) -> str:
    from html import escape

    from utils.resource_provider import provider_label

    name = escape(student_name or "—")
    lines = [f"📁 <b>Учебные ссылки</b> · {name}"]
    if not resources:
        lines.extend([
            "",
            "Лично у этого ученика пока нет ссылок. Глобальные ссылки видны всем.",
        ])
        return "\n".join(lines)
    primary = next((r for r in resources if r.get("is_primary")), None)
    rest = [r for r in resources if r is not primary]
    if primary:
        lines.extend([
            "",
            f"⭐ <b>{escape(primary.get('label') or 'Основная')}</b> · {provider_label(primary.get('provider') or 'other')}",
        ])
    if rest:
        lines.extend(["", f"<b>Дополнительные:</b> {len(rest)}"])
    return "\n".join(lines)


def build_admin_global_resources_text(resources: list) -> str:
    lines = ["🌍 <b>Глобальные учебные ссылки</b>"]
    if not resources:
        lines.extend([
            "",
            "Глобальных ссылок ещё нет. Их видят все ученики на экране «Материалы».",
        ])
        return "\n".join(lines)
    lines.extend(["", f"Всего: {len(resources)}"])
    return "\n".join(lines)


ADMIN_RESOURCE_PROMPT_URL_TEXT = (
    "🔗 Пришлите ссылку на учебную папку или документ.\n\n"
    "Поддерживаются Google Docs/Drive, Filen и любые другие URL — провайдер определится автоматически."
)

ADMIN_RESOURCE_PROMPT_LABEL_TEXT = (
    "✏️ Теперь короткое название (3-30 символов).\n\n"
    "Например: «Курс B1», «Аудио A2», «Грамматика»."
)

ADMIN_RESOURCE_INVALID_URL_TEXT = (
    "⚠️ Это не похоже на ссылку. Пришлите URL вида https://… или /отмена."
)

ADMIN_RESOURCE_INVALID_LABEL_TEXT = (
    "⚠️ Название должно быть от 1 до 60 символов."
)

ADMIN_RESOURCE_PROMPT_PRIMARY_TEXT = (
    "⭐ Сделать эту ссылку основной?\n\n"
    "У ученика может быть только одна основная ссылка — она показывается крупнее всего."
)


# ─── Journey / Onboarding v2 ──────────────────────────────────────────────────

GOAL_PROMPT_TEXT = (
    "🎯 <b>Какая у вас цель в изучении языка?</b>\n\n"
    "Поделитесь короткой формулировкой — например: «уверенно общаться в путешествии», "
    "«читать книги в оригинале», «работать на английском».\n\n"
    "Цель помогает мне понимать, на чём фокусироваться вместе с вами."
)

GOAL_PROMPT_FSM_TEXT = (
    "✏️ Опишите вашу цель в одном-двух предложениях.\n\n"
    "Если передумаете — нажмите «Отмена»."
)

GOAL_SAVED_TEXT = "✅ <b>Цель сохранена.</b>"

GOAL_INVALID_TEXT = (
    "⚠️ Текст слишком короткий или слишком длинный (нужно от 5 до 500 символов)."
)


def build_goal_prompt_message(brand_tone: str | None = None) -> str:
    return choose_tone_variant(
        # strict
        "🎯 <b>Цель занятий</b>\n\n"
        "Сформулируйте цель: что хотите получить от курса. Это влияет на выбор материалов и темп.",
        # neutral
        GOAL_PROMPT_TEXT,
        # warm
        "🎯 <b>Ваша цель</b>\n\n"
        "Опишите коротко, чего хотите достичь.",
        # premium
        "🎯 <b>Ваша цель курса</b>\n\n"
        "Поделитесь личной целью — мы выстроим маршрут именно под неё.",
        tone=brand_tone,
    )


def build_materials_intro_message(brand_tone: str | None = None) -> str:
    return choose_tone_variant(
        "📁 <b>Доступны учебные материалы</b>\n\n"
        "Откройте раздел материалов и ознакомьтесь с подобранными ресурсами.",
        "📁 <b>Учебные материалы готовы</b>\n\n"
        "Откройте раздел материалов — внутри подобраны учебники и ссылки под ваш уровень.",
        "📁 <b>Загляните в материалы</b>\n\n"
        "Я собрал в одном месте всё, что пригодится в первые недели. Откройте — "
        "там быстрее всего сориентироваться.",
        "📁 <b>Ваша библиотека материалов</b>\n\n"
        "Подборка ресурсов уже ждёт вас в разделе материалов.",
        tone=brand_tone,
    )


def build_prep_first_lesson_message(brand_tone: str | None = None) -> str:
    return choose_tone_variant(
        "📅 <b>Первый урок состоится завтра</b>\n\n"
        "Откройте учебный план и пройдите чек-лист подготовки.",
        "📅 <b>Первый урок завтра</b>\n\n"
        "Откройте учебный план — там короткий чек-лист подготовки.",
        "📅 <b>Завтра наш первый урок</b>\n\n"
        "Чтобы он прошёл легко и продуктивно — гляньте чек-лист подготовки в учебном плане. "
        "Если что-то непонятно, напишите мне.",
        "📅 <b>Завтра ваш первый урок</b>\n\n"
        "Чек-лист подготовки уже готов в разделе учебного плана.",
        tone=brand_tone,
    )


def build_feedback_after_first_message(brand_tone: str | None = None) -> str:
    return choose_tone_variant(
        "💬 <b>Оценка первого урока</b>\n\n"
        "Сообщите, как прошёл урок: пожелания и комментарии помогут скорректировать план.",
        "💬 <b>Поделитесь обратной связью</b>\n\n"
        "Расскажите, как прошёл первый урок: что было полезным, что улучшить.",
        "💬 <b>Как прошёл первый урок?</b>\n\n"
        "Поделитесь впечатлениями — что понравилось, что хотелось бы изменить. "
        "Это помогает мне настроить занятия под вас.",
        "💬 <b>Ваши впечатления о первом уроке</b>\n\n"
        "Поделитесь, что было ценным, и я учту это в следующих занятиях.",
        tone=brand_tone,
    )


def build_weekly_checkin_message(brand_tone: str | None = None, *, has_goal: bool = False) -> str:
    if has_goal:
        return choose_tone_variant(
            "🌱 <b>Еженедельная проверка</b>\n\n"
            "Сообщите, движемся ли мы в сторону вашей цели. Корректировки обсудим.",
            "🌱 <b>Еженедельная проверка</b>\n\n"
            "Прошла неделя занятий. Цель в фокусе? Если есть вопросы — напишите.",
            "🌱 <b>Прошла неделя</b>\n\n"
            "Как дела с целью? Если хочется что-то поменять — напишите. "
            "Если двигаемся в нужную сторону — продолжаем.",
            "🌱 <b>Еженедельный обзор</b>\n\n"
            "Цель остаётся в фокусе? Сообщите, если хотите что-то скорректировать.",
            tone=brand_tone,
        )
    return choose_tone_variant(
        "🌱 <b>Итоги первой недели</b>\n\n"
        "Сообщите впечатления и пожелания по формату занятий.",
        "🌱 <b>Прошла неделя</b>\n\n"
        "Поделитесь впечатлениями от первой недели. Что хотелось бы поменять?",
        "🌱 <b>Уже неделя вместе</b>\n\n"
        "Как ощущения от первой недели? Если будет, что обсудить или скорректировать — пишите.",
        "🌱 <b>Первая неделя завершена</b>\n\n"
        "Поделитесь впечатлениями — это поможет настроить дальнейшие занятия.",
        tone=brand_tone,
    )


def build_pair_weekly_report_text(stats: dict, brand_tone: str | None = None) -> str:
    lessons = int(stats.get("lessons_completed") or 0)
    homework = int(stats.get("homework_done") or 0)
    next_lesson = stats.get("next_lesson_at")
    next_str = format_datetime(next_lesson) if next_lesson else "пока не назначен"
    goal = (stats.get("shared_goal_text") or "").strip()

    header = choose_tone_variant(
        "🌱 <b>Итоги недели вашей пары</b>",
        "🌱 <b>Прошла неделя в паре</b>",
        "🌱 <b>Уже неделя вместе как пара</b>",
        "🌱 <b>Еженедельный обзор пары</b>",
        tone=brand_tone,
    )
    body = [
        header,
        "",
        f"📚 Уроков завершено: <b>{lessons}</b>",
        f"✅ ДЗ закрыто: <b>{homework}</b>",
        f"📅 Следующий урок: <b>{html.quote(next_str)}</b>",
    ]
    if goal:
        body.extend(["", f"🎯 Цель в фокусе: <b>{html.quote(goal)}</b>"])
    closing = choose_tone_variant(
        "Сообщите, если что-то нужно скорректировать.",
        "Если будет, что обсудить, — напишите преподавателю.",
        "Если хочется что-то поменять — пишите, обсудим.",
        "Открыты к обсуждению дальнейших шагов.",
        tone=brand_tone,
    )
    body.extend(["", closing])
    return "\n".join(body)


PAIR_GOAL_PROMPT_TEXT = (
    "🎯 <b>Общая цель пары</b>\n\n"
    "Опишите общую цель — то, чего вы хотите достичь вместе. Например: "
    "«пройти A2 до конца лета», «уверенно говорить на интервью», "
    "«готовиться вместе к экзамену».\n\n"
    "Эту цель будут видеть оба участника пары."
)

PAIR_GOAL_PROMPT_FSM_TEXT = (
    "✏️ Напишите общую цель пары одним-двумя предложениями.\n\n"
    "Если передумаете — нажмите «Отмена»."
)

PAIR_GOAL_SAVED_TEXT = (
    "✅ <b>Общая цель сохранена.</b>\n\n"
    "Теперь оба партнёра видят её на главном экране и в еженедельном обзоре."
)

PAIR_GOAL_INVALID_TEXT = (
    "⚠️ Текст слишком короткий или слишком длинный (нужно от 5 до 500 символов)."
)


def build_pair_invite_goal_inherit_text(partner_name: str, goal_text: str) -> str:
    return (
        "🎯 <b>Поддержать цель партнёра?</b>\n\n"
        f"Ваш партнёр <b>{html.quote(partner_name)}</b> уже сформулировал цель:\n"
        f"«{html.quote(goal_text)}»\n\n"
        "Если согласны, я зафиксирую её как общую цель пары — её увидите оба."
    )


def build_journey_progress_text(progress: dict) -> str:
    """Compact one-line progress for the home-screen header."""
    items = [
        ("Тест уровня", progress.get("level_test")),
        ("Цель", progress.get("goal")),
        ("Материалы", progress.get("materials")),
        ("Первый урок", progress.get("first_lesson")),
    ]
    parts = [f"{'✅' if done else '⬜'} {label}" for label, done in items]
    return "Прогресс: " + " · ".join(parts)


def build_first_lesson_payment_invite_text(
    student_name: str,
    requisites: dict,
    pricing_context: dict | None = None,
    speech_style: str | None = None,
    tariff_text: str | None = None,
) -> str:
    requisites_block = build_requisites_text(requisites or {}, pricing_context)
    intro = (
        f"💛 <b>Спасибо за первый урок, {html.quote(student_name)}!</b>"
        if student_name
        else "💛 <b>Спасибо за первый урок!</b>"
    )
    # Auto-derive tariff label from pricing_rate if no explicit tariff_text
    effective_tariff = tariff_text
    if not effective_tariff and pricing_context:
        rate = pricing_context.get("rate")
        if rate and rate.get("label"):
            effective_tariff = format_tariff_display(rate)
    tariff_line = f"\n💳 Тариф: {html.quote(effective_tariff)}\n" if effective_tariff else ""
    next_step = choose_form(
        speech_style,
        "Когда будет удобно, оплатите ближайшую неделю занятий — расписание и темп тогда сохранятся без пауз.",
        "Когда будет удобно, оплати ближайшую неделю занятий — расписание и темп тогда сохранятся без пауз.",
        "Когда будет удобно, оплати неделю занятий — тогда всё будет без пауз 💪",
    )
    confirm = choose_form(
        speech_style,
        "После перевода нажмите <b>«Сообщить об оплате»</b>, и я её отмечу.",
        "После перевода нажми <b>«Сообщить об оплате»</b>, и я её отмечу.",
        "После перевода нажми <b>«Сообщить об оплате»</b> — и готово! 🚀",
    )
    return (
        f"{intro}"
        f"{tariff_line}\n"
        f"Ниже — реквизиты на случай, если ещё не оплачивали.\n\n"
        f"{requisites_block}\n\n"
        f"{next_step}\n"
        f"{confirm}"
    )


def build_first_lesson_payment_invite_text_for_parent(
    parent_name: str,
    child_name: str,
    requisites: dict,
    pricing_context: dict | None = None,
    tariff_text: str | None = None,
) -> str:
    requisites_block = build_requisites_text(requisites or {}, pricing_context)
    greeting = (
        f"💛 <b>Первый урок {html.quote(child_name)} завершён!</b>"
        if child_name
        else "💛 <b>Первый урок завершён!</b>"
    )
    # Auto-derive tariff label from pricing_rate if no explicit tariff_text
    effective_tariff = tariff_text
    if not effective_tariff and pricing_context:
        rate = pricing_context.get("rate")
        if rate and rate.get("label"):
            effective_tariff = format_tariff_display(rate)
    tariff_line = f"\n💳 Тариф: {html.quote(effective_tariff)}" if effective_tariff else ""
    return (
        f"{greeting}\n"
        f"{tariff_line}\n\n"
        f"{requisites_block}\n\n"
        f"Будем рады продолжить занятия. Реквизиты выше."
    ).strip()


def build_contacts_text(info: dict, show_address: bool = False) -> str:
    contacts = info.get("contacts", {})
    lines = [
        "📞 <b>Контакты преподавателя</b>",
    ]
    if contacts.get("project_site_url") or contacts.get("materials_url") or contacts.get("filen_url"):
        lines.extend([
            "",
            "🌐 <b>Сайт и материалы</b>",
            "Там собраны тест уровня и учебные материалы по занятиям.",
        ])
    if contacts.get("phone"):
        lines.append(f"📱 Телефон: <b>{html.quote(contacts['phone'])}</b>")
    if contacts.get("telegram"):
        lines.append(f"💬 Telegram: <b>{html.quote(contacts['telegram'])}</b>")
    if contacts.get("discord"):
        lines.append(f"🎮 Discord: <b>{html.quote(contacts['discord'])}</b>")

    if contacts.get("vk_call") or contacts.get("google_meet"):
        lines.extend([
            "",
            "💻 <b>Онлайн-занятия</b>",
            "VK Звонок — основной вариант, Google Meet — запасной, если нужен VPN.",
        ])

    if show_address and contacts.get("address"):
        lines.extend([
            "",
            "🏠 <b>Очные занятия</b>",
            html.quote(contacts["address"]),
        ])
    elif contacts.get("address"):
        lines.extend([
            "",
            "🏠 <b>Очные занятия</b>",
            "Адрес доступен зарегистрированным ученикам и родителям.",
        ])

    return "\n".join(lines)


def build_registration_step_text(
    step: int,
    total: int,
    question: str,
    *,
    already: list[str] | None = None,
    example: str | None = None,
    note: str | None = None,
) -> str:
    lines = [
        f"<b>Шаг {step}/{total}</b>",
    ]
    cleaned = [item.strip() for item in already or [] if item and item.strip()]
    if cleaned:
        lines.append(f"Уже есть: {html.quote(' · '.join(cleaned))}")
    lines.extend(["", question])
    if example:
        lines.extend(["", f"Например: {example}"])
    lines.extend([
        "",
        note or "Можно ответить коротким текстом. Голосовое преподавателю можно отправить после регистрации.",
    ])
    return "\n".join(lines)


def build_registration_done_text(
    title: str,
    saved_lines: list[str],
    contacts_text: str,
    *,
    next_hint: str = "",
) -> str:
    lines = [
        f"✅ <b>{html.quote(title)}</b>",
        "",
        "<b>Сохранено</b>",
    ]
    lines.extend(saved_lines or ["Данные профиля сохранены."])
    lines.extend([
        "",
        "📞 <b>Контакты и адрес</b>",
        contacts_text,
    ])
    if next_hint:
        lines.extend(["", next_hint])
    return "\n".join(lines)


def build_more_screen_text(role: str) -> str:
    return "👤 <b>Ещё</b>"


def build_help_text() -> str:
    tone = get_brand_tone()
    site_line = choose_tone_variant(
        "↗️ <b>Сайт и материалы</b> — тест уровня и основные материалы преподавателя",
        "↗️ <b>Сайт и материалы</b> — тест уровня, информация о занятиях и полезные материалы",
        "↗️ <b>Сайт и материалы</b> — тест уровня, информация о занятиях и полезные материалы",
        "↗️ <b>Сайт и материалы</b> — тест уровня и материалы по занятиям",
        tone=tone,
    )
    return (
        "🤖 <b>Справка по TutorBot</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — начать работу / войти\n"
        "/menu — главное меню\n"
        "/profile — мой профиль\n"
        "/help — эта справка\n"
        "/freeze — заморозка занятия\n"
        "/plan — учебный план\n"
        "/materials — учебные материалы\n\n"
        "<b>Что есть в боте:</b>\n"
        "📌 <b>Учебный план</b> — фокус, PDF-план и подготовка к уроку\n"
        "📅 <b>Расписание</b> — ближайшие занятия\n"
        "📚 <b>Домашка</b> — активные и выполненные задания\n"
        "💰 <b>Оплата</b> — баланс уроков, история оплат и реквизиты\n"
        "✉️ <b>Написать преподавателю</b> — связаться напрямую\n"
        "📁 <b>Материалы</b> — учебники и раздаточные материалы\n"
        "📞 <b>Контакты</b> — связь, онлайн-занятия и очный адрес\n"
        "👤 <b>Ещё</b> — профиль, заморозка, тест уровня, опасные действия\n"
        f"{site_line}"
    )


def build_brand_tone_text(current_tone: str | None) -> str:
    current_label = brand_tone_label(current_tone)
    current_description = brand_tone_description(current_tone)
    return (
        "🎨 <b>Тональность бренда</b>\n\n"
        f"Текущий режим: <b>{html.quote(current_label)}</b>\n"
        f"{html.quote(current_description)}"
    )


def build_parent_weekly_digest_text(parent_name: str, items: list[dict]) -> str:
    tone = get_brand_tone()
    intro = choose_tone_variant(
        "Короткая сводка по занятиям за неделю:",
        "Короткая сводка по занятиям за неделю:",
        "Короткая сводка по занятиям за неделю:",
        "Короткая сводка по занятиям за неделю:",
        tone=tone,
    )
    lines = [
        "👨‍👩‍👧 <b>Еженедельная сводка</b>",
        "",
        f"{html.quote(parent_name)}, {intro}",
    ]
    for item in items:
        lines.extend([
            "",
            f"• <b>{html.quote(item['student_name'])}</b>",
            f"  📅 Урок за неделю: <b>{'был' if item['had_lesson'] else 'не было'}</b>",
            f"  ⏭ Следующий урок: <b>{html.quote(format_short_datetime(item.get('next_lesson_date')) if item.get('next_lesson_date') else 'не назначен')}</b>",
            f"  📚 Активные ДЗ: <b>{item['active_homework_count']}</b>",
            f"  🎓 Баланс уроков: <b>{lesson_balance_label(item['lesson_balance'])}</b>",
        ])
    return "\n".join(lines)


def build_parent_home_text(parent_name: str, children: list[dict]) -> str:
    lines = [
        "👨‍👩‍👧 <b>Кабинет родителя</b>",
        "",
        f"<b>{html.quote(parent_name)}</b>",
    ]
    if not children:
        lines.extend([
            "",
            "Пока в кабинете нет детей, привязанных к вашему профилю.",
            "Если ребёнок уже занимается, но здесь пусто, напишите преподавателю.",
        ])
        return "\n".join(lines)

    lines.extend(["", "👶 Дети:"])
    for child in children:
        icon = child_traffic_light(child)
        child_name = html.quote(child.get("child_label") or "—")
        summary = child_problem_summary(child)
        lines.append(f"{icon} <b>{child_name}</b> — {html.quote(summary)}")
    return "\n".join(lines)


def build_parent_child_hub_text(child: dict, engagement_mode: str = "active") -> str:
    status = child.get("link_status")
    lines = [
        f"👧 <b>{html.quote(child.get('child_label') or 'Ребёнок')}</b>",
        "",
    ]
    if status != "linked":
        lines.extend([
            "⏳ Этот ребёнок пока сохранён как ориентир по имени и ещё не привязан к активному профилю ученика.",
            "Когда совпадение появится, здесь автоматически откроются расписание, домашка и оплаты.",
        ])
        return "\n".join(lines)

    lines.extend([
        f"{lesson_format_icon(child.get('lesson_format'))} Формат: <b>{lesson_format_label(child.get('lesson_format'))}</b>",
        f"📅 Ближайший урок: <b>{html.quote(format_datetime(child.get('next_lesson_date')) if child.get('next_lesson_date') else 'не назначен')}</b>",
    ])
    if engagement_mode != "trust":
        lines.append(f"📚 Активные ДЗ: <b>{int(child.get('active_homework_count') or 0)}</b>")
    lines.extend([
        f"🎓 Баланс уроков: <b>{lesson_balance_label(child.get('lesson_balance'))}</b>",
    ])
    if engagement_mode == "trust":
        lines.extend([
            "",
            "🌿 <i>Доверительный режим: учёбу контролирует ребёнок и преподаватель. Вы видите расписание и оплаты.</i>",
        ])
    lines.extend(["", ""])
    return "\n".join(lines)


def build_engagement_mode_intro_text(child_name: str) -> str:
    return (
        "🤝 <b>Как вам удобнее быть рядом с учёбой ребёнка?</b>\n\n"
        f"Это последний шаг регистрации для <b>{html.quote(child_name)}</b>.\n\n"
        "🎯 <b>Хочу быть в курсе</b> — кабинет покажет расписание, домашку, учебный план и оплаты. "
        "Подходит, если важно держать руку на пульсе.\n\n"
        "🌿 <b>Доверяю преподавателю</b> — кабинет покажет только расписание и оплаты, без домашки и плана. "
        "Учёбу контролирует ребёнок и преподаватель.\n\n"
        "Этот выбор можно поменять в любой момент в <b>«Ещё → Профиль»</b>."
    )


def build_engagement_mode_switched_text(mode: str) -> str:
    if mode == "trust":
        return (
            "🌿 <b>Режим: доверие преподавателю</b>\n\n"
            "В кабинете ребёнка теперь показываются только расписание и оплаты. "
            "Домашка и учебный план скрыты — за ними следит ребёнок и преподаватель."
        )
    return (
        "🎯 <b>Режим: активное наблюдение</b>\n\n"
        "В кабинете ребёнка снова доступны учебный план и домашка. "
        "Вы видите всё, что относится к учёбе."
    )


def build_requisites_text(req: dict, pricing_context: dict | None = None) -> str:
    lines = [
        "💳 <b>Реквизиты и стоимость</b>",
        "",
    ]
    rate = (pricing_context or {}).get("rate") if pricing_context else None
    if rate:
        group_size = int((pricing_context or {}).get("group_size") or rate.get("group_size") or 1)
        duration = int((pricing_context or {}).get("duration_minutes") or rate.get("duration_minutes") or 90)
        lines.extend([
            "📌 <b>Стоимость занятия</b>",
            f"{html.quote(money_label(rate.get('amount'), rate.get('currency')))} / {duration} минут",
            f"Формат: <b>{group_size} уч.</b>",
        ])
    elif pricing_context:
        group_size = int(pricing_context.get("group_size") or 1)
        duration = int(pricing_context.get("duration_minutes") or 90)
        lines.extend([
            "📌 <b>Стоимость занятия</b>",
            f"Для формата <b>{group_size} уч. · {duration} мин</b> стоимость уточните у преподавателя.",
        ])
    elif req.get("rate"):
        lines.extend([
            "📌 <b>Стоимость занятия</b>",
            html.quote(req["rate"]),
        ])
    if req.get("card"):
        lines.extend([
            "",
            "💳 <b>Карта</b>",
            f"<code>{html.quote(req['card'])}</code>",
        ])
    if req.get("sbp"):
        banks = f" ({html.quote(req['sbp_banks'])})" if req.get("sbp_banks") else ""
        lines.extend([
            "",
            f"📱 <b>СБП</b>{banks}",
            f"<code>{html.quote(req['sbp'])}</code>",
        ])
    if req.get("usdt_trc20"):
        lines.extend([
            "",
            "🪙 <b>USDT TRC-20</b>",
            f"<code>{html.quote(req['usdt_trc20'])}</code>",
        ])
    lines.extend([
        "",
        "Если уже отправили оплату, можно сразу нажать кнопку <b>«Сообщить об оплате»</b> ниже в разделе оплаты.",
    ])
    return "\n".join(lines)


def build_notifications_text(reminders: str | None) -> str:
    return (
        "🔔 <b>Напоминания о занятиях</b>\n\n"
        f"Текущий статус: <b>{html.quote(reminder_status_label(reminders))}</b>\n\n"
        f"{reminder_status_hint(reminders)}"
    )


def _group_active_homework(items: list, today: date) -> list[tuple[str, list]]:
    urgent = []
    upcoming = []
    later = []
    no_deadline = []
    for item in items:
        deadline = item.get("deadline")
        if not deadline:
            no_deadline.append(item)
            continue
        item_date = deadline.date() if isinstance(deadline, datetime) else deadline
        if item_date <= today:
            urgent.append(item)
        elif item_date <= today + timedelta(days=3):
            upcoming.append(item)
        else:
            later.append(item)
    groups = []
    if urgent:
        groups.append(("⏰ <b>Срочно</b>", urgent))
    if upcoming:
        groups.append(("📌 <b>Ближайшее</b>", upcoming))
    if later:
        groups.append(("🗂 <b>Дальше</b>", later))
    if no_deadline:
        groups.append(("📚 <b>Без указанного дедлайна</b>", no_deadline))
    return groups


def build_homework_list_text(items: list, status: str, today: date | None = None) -> str:
    today = today or business_today()
    if status == "done":
        lines = [f"✅ <b>Выполненные задания</b> ({len(items)})"]
        for index, hw in enumerate(items, 1):
            body_html = homework_body_html(
                hw.get("title"),
                hw.get("description"),
                hw.get("attachment_name"),
                hw.get("attachment_mime_type"),
            ) or "—"
            lines.extend([
                "",
                f"✅ <b>{index}. Задание</b>",
                body_html,
                f"📅 Дедлайн: {format_date(hw.get('deadline'))}",
            ])
        return "\n".join(lines)

    lines = [f"📚 <b>Активные задания</b> ({len(items)})"]
    groups = _group_active_homework(items, today)
    if not groups:
        groups = [("📚 <b>Задания</b>", items)]

    counter = 1
    for group_title, group_items in groups:
        lines.extend(["", group_title])
        for hw in group_items:
            body_html = homework_body_html(
                hw.get("title"),
                hw.get("description"),
                hw.get("attachment_name"),
                hw.get("attachment_mime_type"),
            ) or "—"
            lines.extend([
                "",
                f"📝 <b>{counter}. Задание</b>",
                body_html,
                f"📅 Дедлайн: {format_date(hw.get('deadline'))}",
            ])
            counter += 1
    return "\n".join(lines)


def build_homework_empty_text(status: str, *, homework_exempt: bool = False) -> str:
    if status == "done":
        return (
            "✅ <b>Выполненные задания</b>\n\n"
            "Пока здесь пусто. Когда вы отметите задание как выполненное, оно появится в этом разделе."
        )
    if homework_exempt:
        return (
            "📚 <b>Активные задания</b>\n\n"
            "По методике вашего курса домашние задания не задаются. "
            "Если что-то изменится, преподаватель сообщит."
        )
    return (
        "📚 <b>Активные задания</b>\n\n"
        "Сейчас активных домашних заданий нет. Когда преподаватель добавит новое, оно сразу появится здесь."
    )


def build_homework_text(items: list, status: str, *, homework_exempt: bool = False) -> str:
    if not items:
        return build_homework_empty_text(status, homework_exempt=homework_exempt)
    return build_homework_list_text(items, status)


def build_action_result_text(title: str, body: str, next_step: str = "", icon: str = "✅") -> str:
    lines = [f"{icon} <b>{title}</b>", "", body]
    if next_step:
        lines.extend(["", next_step])
    return "\n".join(lines)


def build_reply_sent_text() -> str:
    follow_up = choose_tone_variant(
        "Преподаватель получит его в ближайшее время.",
        "Преподаватель получит его в ближайшее время.",
        "Преподаватель получит его в ближайшее время.",
        "Преподаватель увидит его в ближайшее время.",
        tone=get_brand_tone(),
    )
    return (
        "✅ <b>Сообщение отправлено</b>\n\n"
        f"{follow_up} Если понадобится, можете написать ещё раз из нужного раздела."
    )


def build_homework_done_text(title: str) -> str:
    return (
        "✅ <b>Отлично, отмечено как выполненное</b>\n\n"
        f"Задание «{title}» перенесено в выполненные."
    )


def build_freeze_intro_text(active_count: int) -> str:
    return (
        "❄️ <b>Заморозка занятий</b>\n\n"
        f"Сейчас можно отправить заявку на заморозку для <b>{active_count}</b> активных занятий.\n\n"
        "Выберите причину ниже, а затем мы ещё раз коротко всё подтвердим перед отправкой."
    )


def build_freeze_confirm_text(reason_label: str, active_count: int) -> str:
    lesson_word = "занятия" if active_count % 10 in {2, 3, 4} and active_count % 100 not in {12, 13, 14} else "занятий"
    return (
        "❄️ <b>Подтверждение заморозки</b>\n\n"
        f"Причина: <b>{html.quote(reason_label)}</b>\n"
        f"Будет затронуто: <b>{active_count}</b> {lesson_word}\n\n"
        "После отправки преподаватель увидит заявку и подтвердит её или свяжется с вами для уточнения.\n\n"
        "Если всё верно, отправьте заявку."
    )


def build_freeze_success_text(reason_label: str | None = None, affected_count: int | None = None) -> str:
    details = []
    if reason_label:
        details.append(f"Причина: <b>{html.quote(reason_label)}</b>")
    if affected_count is not None:
        details.append(f"Затронуто занятий: <b>{affected_count}</b>")
    details_block = ("\n" + "\n".join(details) + "\n") if details else "\n"
    return (
        "✅ <b>Заявка на заморозку отправлена</b>\n"
        f"{details_block}\n"
        f"{choose_tone_variant('Преподаватель ответит позже.', 'Преподаватель увидит её и ответит вам, как только сможет.', 'Преподаватель увидит её и ответит вам, как только сможет.', 'Преподаватель увидит заявку и вернётся с ответом, как только сможет.', tone=get_brand_tone())}\n"
        "Пока ничего дополнительно делать не нужно."
    )


def build_self_delete_warning_text(user, snapshot: dict) -> str:
    role = user.get("role")
    full_name = html.quote(user.get("full_name") or "этот профиль")

    if role == "student":
        lines = [
            f"🗑 <b>Удалить профиль {full_name}?</b>",
            "",
            f"📅 Занятий: <b>{snapshot.get('lessons', 0)}</b>",
            f"💳 Оплат: <b>{snapshot.get('payments_as_student', 0)}</b>",
            f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>",
        ]
        if snapshot.get("calendar_links"):
            lines.append(f"🧭 Календарных связей: <b>{snapshot.get('calendar_links', 0)}</b>")
        if snapshot.get("parent_links_as_student"):
            lines.append(f"👨‍👩‍👧 Родительских связей: <b>{snapshot.get('parent_links_as_student', 0)}</b>")
        lines.extend([
            "",
            "После удаления профиль, занятия, оплаты и домашние задания исчезнут из базы.",
            "Вернуться можно будет только через новую регистрацию по <code>/start</code>.",
            "",
            "⚠️ Это действие необратимо.",
        ])
        return "\n".join(lines)

    if role == "parent":
        lines = [
            f"🗑 <b>Удалить родительский профиль {full_name}?</b>",
            "",
            f"👨‍👩‍👧 Связей с учениками: <b>{snapshot.get('parent_links_as_parent', 0)}</b>",
        ]
        if snapshot.get("payments_as_payer"):
            lines.append(f"💳 Оплат как плательщика: <b>{snapshot.get('payments_as_payer', 0)}</b>")
        lines.extend([
            "",
            "Профили учеников при этом не удаляются.",
            "Вернуться можно будет через новую регистрацию по <code>/start</code>.",
            "",
            "⚠️ Это действие необратимо.",
        ])
        return "\n".join(lines)

    return (
        "🗑 <b>Удалить профиль?</b>\n\n"
        "Это действие необратимо. Если хотите продолжить, подтвердите удаление."
    )


def build_self_delete_final_warning_text(role: str | None) -> str:
    if role == "parent":
        return (
            "⚠️ <b>Финальное подтверждение</b>\n\n"
            "Родительский профиль будет удалён без возможности восстановления.\n"
            "Профили учеников сохранятся."
        )
    return (
        "⚠️ <b>Финальное подтверждение</b>\n\n"
        "Профиль, уроки, оплаты и домашние задания будут удалены без возможности восстановления."
    )


def build_self_delete_success_text(role: str | None) -> str:
    if role == "parent":
        return (
            "✅ <b>Родительский профиль удалён</b>\n\n"
            "Связи внутри бота очищены. При необходимости вы сможете зарегистрироваться снова через <code>/start</code>."
        )
    return (
        "✅ <b>Профиль удалён</b>\n\n"
        "Данные очищены из базы бота. Если позже захотите вернуться, просто отправьте <code>/start</code> и пройдите регистрацию заново."
    )


def build_level_test_text(action: str, has_url: bool) -> str:
    if action == "now" and has_url:
        return (
            "🧪 <b>Тест уровня</b>\n\n"
            + choose_tone_variant(
                "Кнопка ниже сразу откроет тест.",
                "Кнопка ниже сразу откроет тест, чтобы можно было пройти его в удобный момент.",
                "Отлично. Кнопка ниже сразу откроет тест, чтобы можно было пройти его в удобный момент.",
                "Кнопка ниже сразу откроет тест в удобный для вас момент.",
                tone=get_brand_tone(),
            )
        )
    if action == "now":
        return (
            "🧪 <b>Тест уровня</b>\n\n"
            "Ссылка на тест пока не добавлена. Напишите преподавателю, и он пришлёт её отдельно."
        )
    if action == "later":
        return (
            "🕒 <b>Хорошо</b>\n\n"
            "Тест можно пройти позже. Кнопка <b>«🧪 Тест уровня»</b> останется в профиле."
        )
    return (
        "🙏 <b>Понял</b>\n\n"
        "Если позже захотите пройти тест, он всё равно будет доступен в профиле."
    )


def build_broadcast_preview_block(mode: str | None, preview_text: str) -> str:
    mode_label = "🧾 <b>Сообщение</b>"
    if mode == "copy":
        mode_label = "🧾 <b>Сообщение с медиа</b>"
    return "\n".join([
        mode_label,
        "",
        preview_text or "—",
    ])


def build_broadcast_preview_text(broadcast_text: str, mode: str | None = "text") -> str:
    return (
        "📢 <b>Предпросмотр рассылки</b>\n\n"
        "Именно так сообщение увидят выбранные ученики:\n\n"
        f"{build_broadcast_preview_block(mode, broadcast_text)}\n\n"
        "Если всё выглядит хорошо, можно перейти к выбору получателей."
    )


def admin_broadcast_recipients_text(preview: str, selected_count: int, total_count: int, mode: str | None = "text") -> str:
    lines = [
        "📢 <b>Выберите получателей рассылки</b>",
        "",
        build_broadcast_preview_block(mode, preview),
        "",
        f"Выбрано: <b>{selected_count}</b> из {total_count}",
    ]
    if total_count and selected_count == total_count:
        lines.append("Сейчас выбраны все ученики. При необходимости снимите лишние отметки.")
    elif selected_count == 0:
        lines.append("Сейчас никто не выбран. Отметьте получателей вручную.")
    else:
        lines.append("Можно точечно добавить или убрать нужных получателей.")
    return "\n".join(lines)


def build_broadcast_send_result_text(sent_count: int, total_count: int) -> str:
    failed = max(total_count - sent_count, 0)
    if failed == 0:
        return (
            "✅ <b>Рассылка завершена</b>\n\n"
            f"Сообщение доставлено <b>{sent_count}</b> из <b>{total_count}</b> получателей."
        )
    return (
        "⚠️ <b>Рассылка завершена частично</b>\n\n"
        f"Доставлено: <b>{sent_count}</b> из <b>{total_count}</b>\n"
        f"Не доставлено: <b>{failed}</b>\n\n"
        "Обычно это значит, что часть пользователей давно не открывала бота или бот им недоступен."
    )


def build_admin_freeze_queue_text(pending_count: int, current_index: int | None = None) -> str:
    if pending_count == 0:
        return (
            "❄️ <b>Заявки на заморозку</b>\n\n"
            "Сейчас активных заявок нет. Как только кто-то отправит новую, она появится здесь."
        )
    lines = [
        "❄️ <b>Заявки на заморозку</b>",
        "",
        f"Сейчас на рассмотрении: <b>{pending_count}</b>.",
    ]
    if current_index is not None:
        lines.append(f"Открыта заявка: <b>{current_index}</b> из {pending_count}.")
    return "\n".join(lines)


def build_admin_freeze_request_text(lesson_id: int, student_name: str, reason_label: str, submitted_at: str) -> str:
    return (
        f"❄️ <b>Заявка #{lesson_id}</b>\n\n"
        f"👤 Ученик: <b>{html.quote(student_name)}</b>\n"
        f"🧭 Причина: <b>{html.quote(reason_label)}</b>\n"
        f"🕒 Отправлена: <b>{html.quote(submitted_at)}</b>\n\n"
        "Выберите решение ниже."
    )


def build_admin_freeze_action_text(action: str, student_name: str, lesson_date: str | None = None) -> str:
    if action == "approve":
        lines = [
            "✅ <b>Заявка одобрена</b>",
            "",
            f"👤 Ученик: <b>{html.quote(student_name)}</b>",
        ]
        if lesson_date:
            lines.append(f"📅 Замороженное занятие: <b>{html.quote(lesson_date)}</b>")
        lines.append("")
        lines.append("Ученик уже получил подтверждение.")
        return "\n".join(lines)
    return (
        "❌ <b>Заявка отклонена</b>\n\n"
        f"👤 Ученик: <b>{html.quote(student_name)}</b>\n\n"
        "Ученик уже получил уведомление, что занятия продолжаются по обычному графику."
    )


def build_admin_dashboard_text(snapshot: dict, ops_status: dict, last_sync_label) -> str:
    if isinstance(last_sync_label, dict):
        last_sync_label = (
            last_sync_label.get("synced_at_local")
            or last_sync_label.get("synced_at")
            or "ещё не запускался"
        )
    elif not last_sync_label:
        last_sync_label = "ещё не запускался"
    scheduler = html.quote(str(ops_status.get("scheduler", "unknown")))
    lines = [
        "🛠 <b>Панель администратора</b>",
        "",
        "🚨 <b>Нужно внимание</b>",
        f"👥 Активных учеников: <b>{snapshot.get('active_students', 0)}</b>",
        f"📅 Уроков сегодня: <b>{snapshot.get('lessons_today', 0)}</b>",
        f"💰 Без уроков на балансе: <b>{snapshot.get('unpaid_students', 0)}</b>",
        f"🕳 Без ближайших уроков: <b>{snapshot.get('students_without_upcoming_lessons', 0)}</b>",
        f"❄️ Заявок на заморозку: <b>{snapshot.get('pending_freezes', 0)}</b>",
        f"📚 Активных ДЗ: <b>{snapshot.get('active_homework', 0)}</b>",
        "",
        "⚙️ <b>Система</b>",
        f"⏱ Планировщик: <b>{scheduler}</b>",
        f"🗓 Последняя синхронизация: <b>{html.quote(last_sync_label)}</b>",
    ]
    return "\n".join(lines)


def build_admin_student_picker_text(students: list, page: int, page_size: int, flow: str) -> str:
    if not students:
        return ADMIN_STUDENTS_EMPTY_TEXT

    flow_titles = {
        "add_lesson": "➕ <b>Добавить занятие</b>",
        "manage_lessons": "🗑 <b>Удалить занятие</b>",
        "add_payment": "💳 <b>Добавить оплату</b>",
        "add_homework": "📚 <b>Задать домашнее задание</b>",
        "calendar_aliases": "🧭 <b>Алиасы Calendar</b>",
        "preview_student": "👨‍🎓 <b>Просмотр как ученик</b>",
        "preview_parent": "👨‍👩‍👧 <b>Просмотр как родитель</b>",
    }
    total_pages = max(1, (len(students) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_items = students[start:start + page_size]

    lines = [flow_titles.get(flow, "👥 <b>Выберите ученика</b>"), ""]
    if total_pages > 1:
        lines.append(f"Страница <b>{page + 1}/{total_pages}</b>")

    for index, student in enumerate(page_items, start + 1):
        next_lesson = format_short_datetime(student.get("next_lesson_date")) if student.get("next_lesson_date") else "не назначен"
        lines.extend([
            "",
            f"<b>{index}. {html.quote(student['full_name'])}</b>",
            f"{lesson_format_icon(student.get('lesson_format'))} {lesson_format_label(student.get('lesson_format'))} · 🎓 {lesson_balance_label(student.get('lesson_balance'))}",
            f"📅 {next_lesson}",
        ])

    footer = "Выберите ученика кнопкой ниже."
    if flow == "preview_parent":
        footer = "Выберите ученика. Открою родительский контур на его данных."
    lines.extend(["", footer])
    return "\n".join(lines)


def build_admin_students_page_text(
    students: list,
    page: int,
    page_size: int,
    filter_label: str = "Все",
    query: str = "",
    sort_label: str = "По имени",
    total_count: int | None = None,
) -> str:
    total_count = total_count if total_count is not None else len(students)
    safe_filter = html.quote(filter_label or "Все")
    safe_query = html.quote(query.strip())
    safe_sort = html.quote(sort_label or "По имени")

    if not students:
        lines = [
            "👥 <b>Список учеников</b>",
            "",
            f"Фильтр: <b>{safe_filter}</b>",
            f"Сортировка: <b>{safe_sort}</b>",
        ]
        if safe_query:
            lines.append(f"Поиск: <b>{safe_query}</b>")
        if total_count:
            lines.extend([
                "",
                "По текущему фильтру ничего не найдено. Измените поиск или сбросьте ограничения.",
            ])
        else:
            lines.extend([
                "",
                "Пока здесь пусто. Как только появятся ученики, список заполнится автоматически.",
            ])
        return "\n".join(lines)

    total_pages = max(1, (len(students) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_items = students[start:start + page_size]

    lines = [
        "👥 <b>Список учеников</b>",
        "",
        f"Показано: <b>{len(students)}</b> из {total_count}",
        f"Фильтр: <b>{safe_filter}</b>",
        f"Сортировка: <b>{safe_sort}</b>",
    ]
    if safe_query:
        lines.append(f"Поиск: <b>{safe_query}</b>")
    if total_pages > 1:
        lines.append(f"Страница <b>{page + 1}/{total_pages}</b>")

    for index, student in enumerate(page_items, start + 1):
        lesson_label = format_short_datetime(student.get("next_lesson_date")) if student.get("next_lesson_date") else "не назначен"
        s_first_dt = student.get("cached_first_lesson_date") or student.get("first_lesson_date")
        s_badge = student_stage_badge(s_first_dt, override=student.get("student_stage_override"))
        lines.extend([
            "",
            f"<b>{index}. {html.quote(student['full_name'])}</b>",
            f"{lesson_format_icon(student.get('lesson_format'))} {lesson_format_label(student.get('lesson_format'))} · {html.quote(student.get('language') or '—')} {html.quote(student.get('level') or '—')} · {s_badge}",
            f"🗣 Обращение: <b>{speech_style_label(student.get('speech_style'))}</b>",
            f"🎓 Баланс: <b>{lesson_balance_label(student.get('lesson_balance'))}</b> · 📅 {lesson_label}",
        ])
        if student.get("pair_title"):
            lines.append(f"👥 Пара: <b>{html.quote(student.get('pair_title'))}</b>")

    lines.extend([
        "",
        "Откройте карточку ученика кнопкой ниже — там будут быстрые действия без лишних переходов.",
    ])
    return "\n".join(lines)


def build_admin_parents_page_text(
    parents: list,
    page: int,
    page_size: int,
    query: str = "",
    total_count: int | None = None,
) -> str:
    total_count = total_count if total_count is not None else len(parents)
    safe_query = html.quote(query.strip())

    if not parents:
        lines = [
            "👨‍👩‍👧 <b>Список родителей</b>",
        ]
        if safe_query:
            lines.extend([
                "",
                f"Поиск: <b>{safe_query}</b>",
                "",
                "По текущему поиску ничего не найдено. Измените запрос или очистите поиск.",
            ])
        else:
            lines.extend([
                "",
                "Пока здесь пусто. Как только появятся родители, список заполнится автоматически.",
            ])
        return "\n".join(lines)

    total_pages = max(1, (len(parents) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_items = parents[start:start + page_size]

    lines = [
        "👨‍👩‍👧 <b>Список родителей</b>",
        "",
        f"Показано: <b>{len(parents)}</b> из {total_count}",
    ]
    if safe_query:
        lines.append(f"Поиск: <b>{safe_query}</b>")
    if total_pages > 1:
        lines.append(f"Страница <b>{page + 1}/{total_pages}</b>")

    for index, parent in enumerate(page_items, start + 1):
        linked_children = int(parent.get("linked_children_count") or 0)
        children_count = int(parent.get("children_count") or 0)
        lines.extend([
            "",
            f"<b>{index}. {html.quote(parent['full_name'])}</b>",
            f"👧 Дети: <b>{linked_children}</b> привязано из <b>{children_count}</b>",
            f"🆔 Telegram ID: <code>{parent['telegram_id']}</code>",
        ])

    lines.extend([
        "",
        "Откройте карточку родителя кнопкой ниже.",
    ])
    return "\n".join(lines)


def build_admin_student_card_text(
    student,
    balance: int,
    next_lesson: datetime | None,
    pair: dict | None = None,
    tariff_text: str | None = None,
    pricing_rate=None,
    progress_block: str | None = None,
) -> str:
    reminders = reminder_status_label(student.get("lesson_reminders"))
    first_dt = student.get("cached_first_lesson_date") or student.get("first_lesson_date")
    override = student.get("student_stage_override")
    badge = student_stage_badge(first_dt, override=override)
    is_overridden = override and override in STUDENT_STAGES
    badge_suffix = " (вручную)" if is_overridden else ""
    completed = int(student.get("lessons_completed_count") or 0)
    # Tariff display: prefer pricing_rate, fallback to tariff_text
    if pricing_rate:
        tariff_display = format_tariff_display(pricing_rate)
    elif tariff_text:
        tariff_display = tariff_text
    else:
        tariff_display = "не назначен"
    lines = [
        f"👤 <b>{html.quote(student['full_name'])}</b>",
        "",
        f"🏷 Стадия: <b>{badge}{badge_suffix}</b> · уроков: {completed}",
        f"{lesson_format_icon(student.get('lesson_format'))} Формат: <b>{lesson_format_label(student.get('lesson_format'))}</b>",
        f"🗣 Обращение: <b>{speech_style_label(student.get('speech_style'))}</b>",
        f"{'🎒' if student.get('student_type') == 'schoolchild' else '🎓'} Тип: <b>{'Школьник' if student.get('student_type') == 'schoolchild' else 'Взрослый'}</b>",
        f"🌍 Язык: <b>{html.quote(student.get('language') or '—')}</b>",
        f"📘 Уровень: <b>{html.quote(student.get('level') or '—')}</b>",
        f"🎓 Баланс: <b>{lesson_balance_label(balance)}</b>",
        f"📅 Ближайший урок: <b>{html.quote(format_datetime(next_lesson) if next_lesson else 'не назначен')}</b>",
        f"⏱ Длительность урока: <b>{lesson_duration_label(student.get('lesson_duration_minutes'))}</b>",
        f"💳 Тариф: <b>{html.quote(tariff_display)}</b>",
        f"🔔 Напоминания: <b>{html.quote(reminders)}</b>",
        f"🆔 Telegram ID: <code>{student['telegram_id']}</code>",
        f"📚 Режим ДЗ: <b>{'не задаю' if student.get('homework_exempt') else 'задаю'}</b>",
    ]
    # Маркер активной заморозки. `frozen_until` — TIMESTAMP; sentinel-год 2100
    # означает «бессрочно».
    from datetime import datetime as _dt_now
    frozen_until = student.get("frozen_until")
    if frozen_until and frozen_until > _dt_now.utcnow():
        if getattr(frozen_until, "year", 0) >= 2100:
            lines.append("❄️ <b>Заморожен бессрочно</b>")
        else:
            lines.append(f"❄️ <b>Заморожен до {frozen_until.strftime('%d.%m.%Y')}</b>")
    carry_over_until = student.get("carry_over_until")
    if carry_over_until:
        from datetime import date as _date_today
        if carry_over_until >= _date_today.today():
            lines.append(
                f"🔁 <b>Защищён от авто-обнуления до {carry_over_until.strftime('%d.%m')}</b>"
            )
    goal_text = (student.get("goal_text") or "").strip()
    if goal_text:
        lines.extend(["", f"🎯 Цель: {html.quote(goal_text)}"])
    pair_label = pair_title_label(pair)
    if pair_label:
        lines.extend([
            "",
            f"👥 <b>Пара:</b> {html.quote(pair_label)}",
            "Операционно ведётся через этот профиль: общий баланс, один темп, одно ДЗ.",
        ])
    if progress_block:
        lines.extend(["", progress_block])
    return "\n".join(lines)


def build_admin_pairs_page_text(pairs: list) -> str:
    lines = [
        "👥 <b>Учебные пары</b>",
        "",
        "Здесь собраны ученики, которые занимаются вдвоём в общем темпе.",
    ]
    if not pairs:
        lines.extend([
            "",
            "Пока нет созданных пар. Можно собрать первую пару из действующего ученика и второго участника.",
        ])
        return "\n".join(lines)

    lines.append(f"Активных пар: <b>{len(pairs)}</b>")
    for index, pair in enumerate(pairs, 1):
        next_lesson = format_short_datetime(pair.get("next_lesson_date")) if pair.get("next_lesson_date") else "не назначен"
        lines.extend([
            "",
            f"<b>{index}. {html.quote(pair_title_label(pair) or 'Пара')}</b>",
            f"Основной контакт: <b>{html.quote(pair.get('primary_student_name') or '—')}</b>",
            f"📅 Следующий урок: <b>{html.quote(next_lesson)}</b>",
            f"📚 Активные ДЗ: <b>{int(pair.get('active_homework_count') or 0)}</b>",
            f"🎓 Общий баланс: <b>{lesson_balance_label(pair.get('lesson_balance'))}</b>",
        ])
    return "\n".join(lines)


def build_admin_pair_card_text(pair: dict) -> str:
    members = [str(name).strip() for name in pair.get("member_names") or [] if str(name).strip()]
    member_lines = [f"• {html.quote(name)}" for name in members] or ["• —"]
    next_lesson = format_datetime(pair.get("next_lesson_date")) if pair.get("next_lesson_date") else "не назначен"
    naming_mode = "ручное" if pair.get("naming_mode") == "manual" else "авто"
    common_surname = (pair.get("common_surname") or "").strip() or "не задана"
    return "\n".join([
        f"👥 <b>{html.quote(pair_title_label(pair) or 'Учебная пара')}</b>",
        "",
        "Участники:",
        *member_lines,
        "",
        f"Основной контакт: <b>{html.quote(pair.get('primary_student_name') or '—')}</b>",
        f"Название: <b>{html.quote(naming_mode)}</b>",
        f"Общая фамилия: <b>{html.quote(common_surname)}</b>",
        "Баланс: <b>общий</b>",
        "Домашнее задание: <b>одно общее</b>",
        "Темп: <b>один на двоих</b>",
        "",
        f"📅 Ближайший урок: <b>{html.quote(next_lesson)}</b>",
        f"📚 Активные ДЗ: <b>{int(pair.get('active_homework_count') or 0)}</b>",
        f"🎓 Баланс уроков: <b>{lesson_balance_label(pair.get('lesson_balance'))}</b>",
    ])


def build_admin_parent_card_text(parent, children: list[dict], payments_as_payer: int) -> str:
    username = parent.get("username")
    username_label = f"@{username}" if username else "не указан"
    status_label = "активен" if parent.get("is_active", True) else "деактивирован"
    lines = [
        f"👨‍👩‍👧 <b>{html.quote(parent['full_name'])}</b>",
        "",
        f"🏷 Статус: <b>{status_label}</b>",
        f"🔗 Username: <b>{html.quote(username_label)}</b>",
        f"💳 Оплат как плательщик: <b>{int(payments_as_payer or 0)}</b>",
        f"👧 Связей с детьми: <b>{len(children)}</b>",
        f"🆔 Telegram ID: <code>{parent['telegram_id']}</code>",
    ]

    if not children:
        lines.extend([
            "",
            "Связанных детей пока нет.",
        ])
        return "\n".join(lines)

    status_labels: dict[object, str] = {
        "linked": "✅ привязан",
        "waiting_link": "⏳ ждёт привязки",
        "inactive_student": "⚠️ ученик неактивен",
    }
    lines.extend([
        "",
        "Дети:",
    ])
    for child in children:
        child_label = html.quote(child.get("child_label") or child.get("student_info") or "Ребёнок")
        status = status_labels.get(child.get("link_status"), "ℹ️ статус неизвестен")
        lines.append(f"• {child_label}  |  {status}")
    return "\n".join(lines)


def _lesson_student_line(lesson: dict) -> str:
    pair_title = (lesson.get("pair_title") or "").strip()
    name = html.quote(lesson.get("full_name") or "—")
    if pair_title:
        return f"👥 Пара: <b>{html.quote(pair_title)}</b>"
    return f"👤 Ученик: <b>{name}</b>"


def build_teacher_lesson_followup_text(lesson: dict) -> str:
    return "\n".join([
        "🧾 <b>Урок завершился</b>",
        "",
        _lesson_student_line(lesson),
        f"📅 Урок: <b>{html.quote(format_datetime(lesson.get('lesson_date')))}</b>",
        f"{lesson_format_icon(lesson.get('lesson_format'))} Формат: <b>{lesson_format_label(lesson.get('lesson_format'))}</b>",
        "",
        "Как прошёл урок?",
        "Ниже можно сохранить приватный комментарий и закладку по учебнику или книге.",
    ])


def build_teacher_bookmark_reminder_text(lesson: dict) -> str:
    is_offline = (lesson.get("lesson_format") or "online") == "offline"
    lead_label = "за 1 час" if is_offline else "за 30 минут"
    lines = [
        "📖 <b>Закладка перед уроком</b>",
        "",
        _lesson_student_line(lesson),
        f"📅 Урок: <b>{html.quote(format_datetime(lesson.get('lesson_date')))}</b>",
        f"{lesson_format_icon(lesson.get('lesson_format'))} Формат: <b>{lesson_format_label(lesson.get('lesson_format'))}</b>",
        f"⏰ Напоминание: <b>{lead_label}</b>",
        "",
    ]

    bookmark_state = lesson.get("current_bookmark_state") or "empty"
    bookmark_text = lesson.get("current_bookmark_text") or ""
    if bookmark_state == "saved" and bookmark_text:
        lines.extend([
            "📍 <b>Текущая закладка</b>",
            bookmark_text,
        ])
    elif bookmark_state == "no_material":
        lines.append("🚫 По учебнику или книге на прошлом уроке не работали, актуальной закладки сейчас нет.")
    else:
        lines.append("📭 Закладка для этого ученика пока не сохранена.")

    return "\n".join(lines)


def build_admin_payments_text(student_name: str, balance: int, payments: list) -> str:
    if not payments:
        return "\n".join([
            f"💰 <b>Оплаты: {student_name}</b>",
            "",
            f"Сейчас на балансе: <b>{lesson_balance_label(balance)}</b>",
            "История оплат пока пустая.",
        ])

    lines = [
        f"💰 <b>Оплаты: {student_name}</b>",
        "",
        f"Текущий баланс: <b>{lesson_balance_label(balance)}</b>",
        "",
        "Последние оплаты:",
    ]
    for index, payment in enumerate(payments, 1):
        lines.extend([
            "",
            f"{index}. <b>{int(payment['amount'])} ₽</b> · {payment['lessons_count']} ур.",
            f"   📅 {format_date(payment.get('payment_date'))}",
            f"   🎓 Остаток: {lesson_balance_label(payment.get('lessons_remaining'))}",
        ])
    lines.extend(["", "Ниже можно быстро удалить лишнюю запись, если это нужно."])
    return "\n".join(lines)


def build_admin_homework_list_text(items: list) -> str:
    if not items:
        return "📋 <b>Активные ДЗ</b>\n\nСейчас активных заданий нет."
    lines = [f"📋 <b>Активные ДЗ</b> ({len(items)})"]
    for item in items:
        body_html = homework_body_html(
            item.get("title"),
            item.get("description"),
            item.get("attachment_name"),
            item.get("attachment_mime_type"),
        ) or "—"
        badge = delivery_badge(item)
        deadline_line = f"  📅 До {format_date(item.get('deadline'))}"
        if badge:
            deadline_line += f"  |  {html.quote(badge)}"
        lines.extend([
            "",
            f"• <b>{html.quote(item['full_name'])}</b>",
            f"  📝 Задание:\n{body_html}",
            deadline_line,
        ])
    lines.extend(["", "Выберите задание ниже, если нужно открыть, отредактировать или удалить его."])
    return "\n".join(lines)


def build_homework_template_draft(student_name: str | None, materials: list, language: str | None = None) -> str:
    materials = list(materials or [])[:3]
    if not materials:
        return ""

    lines: list[str] = []
    student_name = (student_name or "").strip()
    if student_name:
        lines.append(f"• {student_name}")
    lines.append("📝 Задание:")

    for index, item in enumerate(materials, start=1):
        title = _homework_template_title(item, language)
        lines.extend(["", f"{index}. {title}."])

        if _is_vocabulary_material(item):
            url = _extract_template_url(str(_item_value(item, "raw_fragment") or ""))
            if _is_french_language(language):
                text = "Apprenez des nouvelles expressions ici"
            else:
                text = "Learn new words here"
            lines.append(f"{text}: {url}." if url else f"{text}:")
            continue

        progress = _homework_template_progress(item)
        if progress:
            lines.append(progress)

    return "\n".join(lines)


def _is_french_language(language: str | None) -> bool:
    return "фран" in (language or "").strip().lower() or "fr" == (language or "").strip().lower()


def _is_vocabulary_material(item) -> bool:
    kind = str(_item_value(item, "material_kind") or "").strip().lower()
    title = str(_item_value(item, "material_title") or "").strip().lower()
    return kind == "vocabulary" or "vocabulary" in title or "vocabulaire" in title


def _homework_template_title(item, language: str | None) -> str:
    if _is_vocabulary_material(item):
        return "Le vocabulaire" if _is_french_language(language) else "Vocabulary"
    title = str(_item_value(item, "material_title") or "").strip() or "Материал"
    return title.rstrip(" .")


def _homework_template_progress(item) -> str:
    exercise = str(_item_value(item, "exercise_label") or "").strip()
    page_from = _item_value(item, "page_from")
    page_to = _item_value(item, "page_to")
    parts = []
    if exercise:
        parts.append(exercise.rstrip(" .;"))
    if page_from:
        if page_to and page_to != page_from:
            parts.append(f"pages {page_from}-{page_to}")
        else:
            parts.append(f"page {page_from}")
    return f"{' — '.join(parts)};" if parts else ""


def _extract_template_url(value: str) -> str:
    import re

    match = re.search(r"https?://\S+", value or "")
    if not match:
        return ""
    return match.group(0).rstrip(".,;)")


def build_admin_homework_description_prompt(
    student_name: str | None,
    recent_mentions: list,
    top_materials: list,
    latest_mention,
    has_homework_history: bool,
    template_draft: str | None = None,
) -> str:
    student_name = (student_name or "").strip()
    intro = []
    if student_name:
        intro = [
            "📝 <b>Новое домашнее задание</b>",
            "",
            f"👤 Ученик: <b>{html.quote(student_name)}</b>",
            "",
        ]

    template_draft = (template_draft or "").strip()
    if not template_draft:
        return ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT

    lines = intro + [
        "📋 <b>Черновик по статистике</b>",
        f"<pre>{html.quote(template_draft)}</pre>",
    ]

    lines.extend(["", ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT])
    return "\n".join(lines)


def build_admin_today_text(snapshot: dict, today_date) -> str:
    if hasattr(today_date, "strftime"):
        date_label = today_date.strftime("%-d %B %Y")
    else:
        date_label = str(today_date)

    lessons: list[dict] = snapshot.get("lessons_today") or []
    unpaid: int = int(snapshot.get("unpaid_count") or 0)
    missing_hw: int = int(snapshot.get("missing_homework_count") or 0)
    pending_freeze: int = int(snapshot.get("pending_freeze_count") or 0)
    unanswered: int = int(snapshot.get("unanswered_replies_count") or 0)

    lines = [f"🎯 <b>Сегодня · {html.quote(date_label)}</b>", ""]

    online_count = sum(1 for l in lessons if (l.get("lesson_format") or "online") != "offline")
    offline_count = len(lessons) - online_count

    if lessons:
        count_parts = []
        if online_count:
            count_parts.append(f"{online_count} онлайн")
        if offline_count:
            count_parts.append(f"{offline_count} очно")
        count_suffix = f" ({' / '.join(count_parts)})" if count_parts else ""
        lines.append(f"📅 Уроки сегодня: <b>{len(lessons)}{count_suffix}</b>")
        for i, lesson in enumerate(lessons):
            prefix = "└" if i == len(lessons) - 1 else "├"
            fmt_label = "очно" if (lesson.get("lesson_format") or "online") == "offline" else "онлайн"
            lines.append(
                f"   {prefix} {html.quote(lesson['time'])} · {html.quote(lesson['full_name'])} ({fmt_label})"
            )
    else:
        lines.append("📅 Уроков сегодня: <b>0</b>")

    lines.append("")

    attention_items = []
    if unpaid:
        attention_items.append(
            f"• {unpaid} {_plural(unpaid, 'ученик без оплаты', 'ученика без оплаты', 'учеников без оплаты')} на следующую неделю"
        )
    if missing_hw:
        attention_items.append(
            f"• {missing_hw} {_plural(missing_hw, 'ученик', 'ученика', 'учеников')} — ДЗ перед завтрашним уроком не задано"
        )
    if pending_freeze:
        attention_items.append(
            f"• {pending_freeze} {_plural(pending_freeze, 'заявка на заморозку ждёт', 'заявки на заморозку ждут', 'заявок на заморозку ждут')} решения"
        )
    if unanswered:
        attention_items.append(
            f"• {unanswered} {_plural(unanswered, 'ответ ученика', 'ответа учеников', 'ответов учеников')} за последние сутки"
        )

    hard_feedback: list[dict] = snapshot.get("hard_feedback") or []
    for fb in hard_feedback:
        attention_items.append(
            f"• 😕 Сложный урок: {html.quote(fb.get('full_name', '?'))} ({html.quote(fb.get('date', ''))})"
        )

    if attention_items:
        lines.append("⚠️ <b>Внимание сегодня:</b>")
        lines.extend(attention_items)
    else:
        lines.append("✅ <b>Всё в порядке</b> — нет срочных задач.")

    return "\n".join(lines)


def _plural(n: int, form1: str, form2: str, form5: str) -> str:
    n_abs = abs(n)
    n_mod100 = n_abs % 100
    n_mod10 = n_abs % 10
    if 11 <= n_mod100 <= 19:
        return form5
    if n_mod10 == 1:
        return form1
    if 2 <= n_mod10 <= 4:
        return form2
    return form5


# ─── Parent traffic lights ────────────────────────────────────────────────────

def child_traffic_light(child_overview) -> str:
    if isinstance(child_overview, dict):
        get = child_overview.get
    else:
        def get(k, d=None):
            try:
                return child_overview[k]
            except Exception:
                return d

    link_status = get("link_status")
    if link_status not in ("linked",):
        return "⏳"

    next_lesson_date = get("next_lesson_date")
    lesson_balance = int(get("lesson_balance") or 0)
    overdue_homework_count = int(get("overdue_homework_count") or 0)

    if lesson_balance == 0 or next_lesson_date is None:
        return "🔴"

    if lesson_balance <= 1 or overdue_homework_count > 0:
        return "🟡"

    return "🟢"


def child_problem_summary(child_overview) -> str:
    if isinstance(child_overview, dict):
        get = child_overview.get
    else:
        def get(k, d=None):
            try:
                return child_overview[k]
            except Exception:
                return d

    link_status = get("link_status")
    if link_status not in ("linked",):
        return "ждём подтверждения связи"

    next_lesson_date = get("next_lesson_date")
    lesson_balance = int(get("lesson_balance") or 0)
    overdue_homework_count = int(get("overdue_homework_count") or 0)

    if lesson_balance == 0:
        return "нет оплаченных уроков"
    if next_lesson_date is None:
        return "нет ближайшего урока"
    if overdue_homework_count > 0:
        days = overdue_homework_count
        if days == 1:
            return f"ДЗ просрочено на {days} день"
        elif 2 <= days <= 4:
            return f"ДЗ просрочено на {days} дня"
        else:
            return f"ДЗ просрочено на {days} дней"
    if lesson_balance <= 1:
        return "остался 1 урок на балансе"

    if isinstance(next_lesson_date, datetime):
        return f"урок {next_lesson_date.strftime('%d.%m в %H:%M')}, всё в норме"
    return "всё в норме"


# ─── Stateful student CTA ─────────────────────────────────────────────────────

def compute_student_cta(
    user,
    balance: int,
    next_lesson: datetime | None,
    active_homework: list,
    homework_overdue_count: int,
) -> dict | None:
    now = datetime.now()

    if next_lesson is not None:
        delta = next_lesson - now
        minutes_until = delta.total_seconds() / 60
        if 0 <= minutes_until <= 15:
            mins = int(minutes_until)
            if user is not None and isinstance(user, dict):
                vk_url = (
                    (user.get("contacts") or {}).get("vk_call")
                    if isinstance(user.get("contacts"), dict)
                    else None
                )
            else:
                vk_url = None
            cta: dict = {
                "kind": "vk_call",
                "text": f"⏰ Урок начинается через {mins} мин.",
                "button_label": "📞 VK Звонок",
            }
            if vk_url:
                cta["button_url"] = vk_url
            else:
                cta["button_callback"] = "contacts"
            return cta

    if homework_overdue_count > 0:
        hw = active_homework[0] if active_homework else None
        title = (hw.get("title") or "ДЗ") if hw else "ДЗ"
        if len(title) > 30:
            title = title[:28] + "…"
        return {
            "kind": "overdue_homework",
            "text": f"⚠️ Просрочено ДЗ: «{title}»",
            "button_label": "📚 Открыть ДЗ",
            "button_callback": "homework",
        }

    if balance == 0:
        return {
            "kind": "zero_balance",
            "text": "💸 На балансе нет уроков. Оплатите ближайшую неделю.",
            "button_label": "💰 Оплата",
            "button_callback": "payment",
        }

    if user is not None:
        level = (user.get("level") or "").strip() if isinstance(user, dict) else ""
        first_lesson_date = user.get("first_lesson_date") if isinstance(user, dict) else None
        if not level or level == "unknown":
            if first_lesson_date is None:
                return {
                    "kind": "level_test",
                    "text": "🧪 Пройдите тест уровня — это 10 минут.",
                    "button_label": "🧪 Тест уровня",
                    "button_callback": "level_test:now",
                }

    return None


# ─── Admin Inbox text builders ────────────────────────────────────────────────

_INBOX_KIND_LABELS: dict[str, str] = {
    "reply": "Сообщение",
    "freeze_request": "Заявка на заморозку",
    "first_contact": "Первый контакт (родитель)",
}

_INBOX_CONTEXT_LABELS: dict[str, str] = {
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


def _inbox_payload(event) -> dict:
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return payload


def build_admin_inbox_text(events: list) -> str:
    unread_count = sum(1 for e in events if not e.get("handled_at"))
    lines = [
        "💬 <b>Входящие</b>",
        f"Непрочитанных: <b>{unread_count}</b>" if unread_count else "Нет непрочитанных.",
    ]
    if not events:
        return "\n".join(lines)

    today_date = datetime.now().date()
    yesterday_date = today_date - timedelta(days=1)

    today_items = []
    yesterday_items = []
    older_items = []

    for event in events:
        created_at = event.get("created_at")
        if isinstance(created_at, datetime):
            event_date = created_at.date()
        else:
            event_date = None
        if event_date == today_date:
            today_items.append(event)
        elif event_date == yesterday_date:
            yesterday_items.append(event)
        else:
            older_items.append(event)

    def _format_event(event) -> str:
        payload = _inbox_payload(event)
        name = (payload.get("full_name") or "—")[:20]
        context = payload.get("context") or event.get("kind") or "—"
        context_label = _INBOX_CONTEXT_LABELS.get(context, context)
        created_at = event.get("created_at")
        time_str = created_at.strftime("%H:%M") if isinstance(created_at, datetime) else "—"
        preview = (payload.get("message_preview") or "")[:50]
        handled = "✓" if event.get("handled_at") else ""
        return f"{handled}• {time_str} · {html.quote(name)} ({html.quote(context_label)}): «{html.quote(preview)}»"

    if today_items:
        lines.extend(["", "🆕 <b>Сегодня</b>"])
        lines.extend(_format_event(e) for e in today_items)

    if yesterday_items:
        lines.extend(["", "📬 <b>Вчера</b>"])
        lines.extend(_format_event(e) for e in yesterday_items)

    if older_items:
        lines.extend(["", "📁 <b>Ранее</b>"])
        lines.extend(_format_event(e) for e in older_items)

    return "\n".join(lines)


def build_admin_inbox_item_text(event) -> str:
    payload = _inbox_payload(event)
    kind = event.get("kind") or "—"
    kind_label = _INBOX_KIND_LABELS.get(kind, kind)
    name = html.quote(payload.get("full_name") or "—")
    context = payload.get("context") or kind
    context_label = _INBOX_CONTEXT_LABELS.get(context, context)
    created_at = event.get("created_at")
    dt_str = created_at.strftime("%d.%m.%Y %H:%M") if isinstance(created_at, datetime) else "—"
    preview = html.quote((payload.get("message_preview") or "—")[:500])
    handled = event.get("handled_at")

    lines = [
        f"📨 <b>{kind_label}</b>",
        "",
        f"👤 {name}",
        f"🧭 Контекст: <b>{html.quote(context_label)}</b>",
        f"📅 {dt_str}",
        f"Статус: {'✅ Закрыто' if handled else '🆕 Открыто'}",
        "",
        f"💬 {preview}",
    ]
    return "\n".join(lines)


# ── Homework nudge messages ─────────────────────────────────────────────────

def build_nudge_message(full_name: str, stage: int, hours_since: int) -> str:
    """Build the text for a homework nudge at the given escalation stage.

    Stage 1: gentle reminder.
    Stage 2: warning.
    Stage 3: urgent, 24h passed.
    """
    if stage == 1:
        return f"📝 {full_name}: урок закончился {hours_since}ч назад, ДЗ не отправлено."
    elif stage == 2:
        return f"⚠️ {full_name} ждёт домашку. Уже {hours_since}ч без ДЗ."
    else:
        return f"🔴 {full_name}: сутки без ДЗ после урока."


# ── Balance transactions ────────────────────────────────────────────────────

_TX_EMOJI = {
    "payment_added": "💳",
    "lesson_consumed": "📖",
    "no_show": "⚠️",
    "manual_adjustment": "🔧",
    "admin_writeoff": "🔄",
}

_TX_LABEL = {
    "payment_added": "Оплата",
    "lesson_consumed": "Урок",
    "no_show": "Прогул",
    "manual_adjustment": "Корректировка",
    "admin_writeoff": "Списание",
}


def build_transaction_history_text(balance: int, transactions: list) -> str:
    lines = [
        "💰 <b>Оплата</b>",
        "",
        f"Сейчас на балансе: <b>{lesson_balance_label(balance)}</b>",
    ]
    if not transactions:
        lines.extend(["", "История пока пуста."])
        return "\n".join(lines)

    lines.extend(["", "📋 <b>История:</b>"])
    running = balance
    entries = []
    for tx in transactions:
        dt = tx.get("created_at")
        date_str = dt.strftime("%d.%m") if dt else "—"
        emoji = _TX_EMOJI.get(tx["type"], "•")
        amount = int(tx["amount_lessons"])
        sign = f"+{amount}" if amount > 0 else str(amount)
        label = _TX_LABEL.get(tx["type"], tx["type"])
        extra = ""
        if tx["type"] == "payment_added" and tx.get("payment_amount"):
            extra = f" ({int(tx['payment_amount'])} ₽)"
        entries.append(f"  {date_str} {emoji} {label} {sign}{extra} (ост. {running})")
        running -= amount

    lines.extend(entries)
    return "\n".join(lines)


# ── Finance analytics ────────────────────────────────────────────────────────

def build_finance_text(
    income_week: float,
    income_month: float,
    discipline: list,
    forecast_week: float,
    forecast_month: float,
    lost_pct: float,
    tariff_stats: list,
) -> str:
    lines = ["💰 <b>Финансы</b>", ""]

    lines.append("📈 <b>Доход</b>")
    lines.append(f"  Эта неделя: <b>{int(income_week)} ₽</b>")
    lines.append(f"  Этот месяц: <b>{int(income_month)} ₽</b>")
    lines.append("")

    overdue = [d for d in discipline if d["balance"] <= 0 and d.get("last_payment_at")]
    on_time = len(discipline) - len(overdue)
    lines.append("📋 <b>Дисциплина</b>")
    lines.append(f"  ✅ Вовремя: {on_time}")
    if overdue:
        lines.append(f"  ⚠️ Задержка: {len(overdue)}")
        from datetime import datetime
        now = datetime.now()
        for d in overdue:
            days = (now - d["last_payment_at"]).days if d["last_payment_at"] else 0
            lines.append(f"    — {d['full_name']} ({days} дн.)")
    lines.append("")

    lines.append("🔮 <b>Прогноз</b>")
    lines.append(f"  Следующая неделя: ~{int(forecast_week)} ₽")
    lines.append(f"  Следующий месяц: ~{int(forecast_month)} ₽")
    if lost_pct > 0:
        lines.append(f"  Поправка на потери: -{lost_pct:.0f}%")
    lines.append("")

    if tariff_stats:
        lines.append("📊 <b>Тарифы</b>")
        for ts in tariff_stats:
            label = ts.get("label") or f"{ts['group_size']}×{ts['duration_minutes']}"
            count = int(ts["student_count"])
            rate = int(ts["amount"])
            monthly = rate * count * 4
            lines.append(f"  {label} ({rate} ₽): {count} уч. → {monthly} ₽/мес")

    return "\n".join(lines)


def build_finance_briefing_block(income_week: float, overdue_names: list[str]) -> str:
    lines = [f"💰 Доход за неделю: {int(income_week)} ₽"]
    if overdue_names:
        lines.append(f"⚠️ Ожидают оплаты: {', '.join(overdue_names)}")
    return "\n".join(lines)


# ── Work rules ────────────────────────────────────────────────────────────────

def build_work_rules_text(rules: list) -> str:
    if not rules:
        return "📜 <b>Правила работы</b>\n\nПравила пока не добавлены."
    lines = ["📜 <b>Правила работы</b>", ""]
    for i, rule in enumerate(rules, 1):
        lines.append(f"<b>{i}. {html.quote(rule['title'])}</b>")
        lines.append(f"   {html.quote(rule['body'])}")
        lines.append("")
    return "\n".join(lines)


def build_admin_work_rules_text(rules: list) -> str:
    if not rules:
        return "📜 <b>Правила работы</b>\n\nПравил пока нет. Добавьте первое правило."
    lines = ["📜 <b>Правила работы</b>", ""]
    for i, rule in enumerate(rules, 1):
        lines.append(f"<b>{i}. {html.quote(rule['title'])}</b>")
        lines.append(f"   {html.quote(rule['body'])}")
        lines.append("")
    return "\n".join(lines)


def build_onboarding_rules_text(rules: list) -> str:
    if not rules:
        return ""
    lines = [
        "📜 <b>Правила работы</b>",
        "",
        "Перед началом занятий, ознакомьтесь с правилами:",
        "",
    ]
    for i, rule in enumerate(rules, 1):
        lines.append(f"<b>{i}. {html.quote(rule['title'])}</b>")
        lines.append(f"   {html.quote(rule['body'])}")
        lines.append("")
    return "\n".join(lines)


# ── No-show ───────────────────────────────────────────────────────────────────

def build_no_show_confirm_text(lesson: dict, student_name: str, balance: int) -> str:
    date_str = format_datetime(lesson.get("lesson_date")) if lesson.get("lesson_date") else "—"
    new_balance = balance - 1
    return "\n".join([
        "⚠️ <b>Списать урок как прогул?</b>",
        "",
        f"👤 {html.quote(student_name)}",
        f"📅 {html.quote(date_str)}",
        "",
        f"Баланс сейчас: {balance} → станет: {new_balance}",
    ])


def build_no_show_notification_text(lesson_date, balance: int) -> str:
    date_str = format_datetime(lesson_date) if lesson_date else "—"
    return "\n".join([
        f"⚠️ Урок {html.quote(date_str)} списан по правилам (неявка).",
        f"📊 Текущий баланс: {lesson_balance_label(balance)}.",
    ])


# ── Payment push ──────────────────────────────────────────────────────────────

def build_payment_added_notification_text(amount: float, lessons: int, balance: int) -> str:
    return "\n".join([
        "✅ <b>Оплата принята!</b>",
        "",
        f"💰 Сумма: {int(amount)} ₽",
        f"🎓 Уроков добавлено: {lessons}",
        f"📊 Текущий баланс: {lesson_balance_label(balance)}",
    ])
