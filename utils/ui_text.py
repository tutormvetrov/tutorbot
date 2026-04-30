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


def _fix_utf8_mojibake(value: str) -> str:
    try:
        return value.encode("cp1251").decode("utf-8")
    except Exception:
        return value

MAIN_MENU_TEXT = "📍 <b>Главное меню</b>\n\nВыберите, что нужно сейчас."
ACTION_CANCELLED_TEXT = "❌ Действие отменено."
REGISTRATION_REQUIRED_TEXT = "⚠️ Сначала зарегистрируйтесь через /start"
DEACTIVATED_ACCOUNT_TEXT = "⛔️ Ваш аккаунт деактивирован. Обратитесь к преподавателю."
BLOCKED_ACCOUNT_TEXT = _fix_utf8_mojibake("рџљ« Р”РѕСЃС‚СѓРї Рє Р±РѕС‚Сѓ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ. Р•СЃР»Рё СЌС‚Рѕ РѕС€РёР±РєР°, РѕР±СЂР°С‚РёС‚РµСЃСЊ Рє РїСЂРµРїРѕРґР°РІР°С‚РµР»СЋ.")
BLOCKED_ACCOUNT_ALERT = _fix_utf8_mojibake("Р”РѕСЃС‚СѓРї Рє Р±РѕС‚Сѓ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ.")

ADMIN_HOME_TEXT = (
    "🛠 <b>Панель администратора</b>\n\n"
    "Сверху — живая сводка по боту. Ниже — четыре рабочих раздела."
)
ADMIN_STUDENTS_CATEGORY_TEXT = (
    "👥 <b>Ученики</b>\n\n"
    "Сначала откройте список учеников или родителей, либо добавьте нового ученика.\n"
    "Здесь же находятся формат занятий, обращение и действия по доступу."
)
ADMIN_EDUCATION_CATEGORY_TEXT = (
    "📚 <b>Учебный процесс</b>\n\n"
    "Здесь собраны все учебные действия: занятия, оплаты, домашние задания и заморозки."
)
ADMIN_COMMUNICATION_CATEGORY_TEXT = (
    "📢 <b>Коммуникации</b>\n\n"
    "Рассылки, ответы ученикам и служебные сообщения."
)
ADMIN_SERVICE_CATEGORY_TEXT = (
    "⚙️ <b>Сервис</b>\n\n"
    "Здесь собраны мониторинг бота и рабочий проектный контекст."
)
ADMIN_SERVICE_MONITORING_TEXT = (
    "📊 <b>Мониторинг</b>\n\n"
    "Здесь собраны синхронизация Calendar, отчёты и здоровье бота."
)
ADMIN_SERVICE_CONTEXT_TEXT = (
    "🧠 <b>Контекст и проект</b>\n\n"
    "Здесь лежат тональность бренда и рабочие заметки для следующих сессий."
)
ADMIN_SYNC_IN_PROGRESS_TEXT = "🔄 Синхронизирую Google Calendar..."
ADMIN_SYNC_ERROR_HINT = (
    "Проверьте путь в <b>GOOGLE_CREDENTIALS_FILE</b> "
    "и корректность <b>GOOGLE_CALENDAR_ID</b>."
)

ADMIN_NO_REGISTERED_STUDENTS_TEXT = "⚠️ Нет зарегистрированных учеников."
ADMIN_NO_ACTIVE_STUDENTS_TEXT = "👥 Нет активных учеников."
ADMIN_STUDENTS_EMPTY_TEXT = "👥 <b>Список учеников</b>\n\nПока здесь пусто. Как только появятся ученики, список заполнится автоматически."
ADMIN_PARENTS_EMPTY_TEXT = "👨‍👩‍👧 <b>Список родителей</b>\n\nПока здесь пусто. Как только появятся родители, список заполнится автоматически."
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
ADMIN_HEALTH_NO_ERRORS_TEXT = "✅ В последних runtime-логах ошибок не найдено."

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


def student_freshness_label(first_lesson_date: datetime | None, today: date | None = None) -> str:
    if not first_lesson_date:
        return "новый"
    today = today or business_today()
    rollover_date = _add_calendar_month(first_lesson_date.date())
    return "старый" if today >= rollover_date else "новый"


def student_freshness_badge(first_lesson_date: datetime | None, today: date | None = None) -> str:
    label = student_freshness_label(first_lesson_date, today=today)
    return "🆕 новый" if label == "новый" else "📘 старый"


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
        return "Сейчас напоминания не приходят. Их можно включить в один клик."
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
    lines.extend([
        f"📅 Ближайший урок: <b>{html.quote(next_lesson_text)}</b>",
        f"📚 Активные ДЗ: <b>{int(active_homework_count or 0)}</b>",
        f"🎓 Баланс: <b>{lesson_balance_label(balance)}</b>",
        "",
    ])

    if next_lesson and active_homework_count:
        lines.append("Сначала стоит проверить расписание и домашние задания.")
    elif next_lesson:
        lines.append("Ниже собраны расписание, оплата, профиль и связь с преподавателем.")
    else:
        lines.append("Начните с расписания или напишите преподавателю, если нужен новый урок.")
    return "\n".join(lines)


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
    if (next_lesson_format or "online") == "offline":
        hint = "Адрес очного урока всегда можно открыть в разделе <b>Контакты</b>."
    else:
        hint = "Ссылки и способы подключения к онлайн-уроку собраны в разделе <b>Контакты</b>."
    return title + "\n\n" + "\n".join(lines) + f"\n\n{hint}"


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


def build_payment_text(balance: int, payments: list) -> str:
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
        "Ниже — последние оплаты и текущий остаток по каждой из них.",
        "",
        "💳 <b>История оплат</b>",
    ])
    for index, payment in enumerate(payments, 1):
        date_str = format_date(payment.get("payment_date"))
        lines.extend([
            "",
            f"{index}. <b>{int(payment['amount'])} ₽</b> · {payment['lessons_count']} ур.",
            f"   📅 {date_str}",
            f"   🎓 Остаток по этой оплате: {lesson_balance_label(payment.get('lessons_remaining'))}",
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
        "📄 <b>Preview PDF-плана</b>",
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
        lines.append(
            f"• <b>{int(rate['group_size'])} уч.</b> · "
            f"{int(rate['duration_minutes'])} мин · "
            f"<b>{html.quote(money_label(rate['amount'], rate.get('currency')))}</b>"
        )
    return "\n".join(lines)


def build_materials_text(materials_url: str = "", website_url: str = "") -> str:
    lines = ["📁 <b>Учебные материалы</b>"]
    if materials_url:
        lines.extend([
            "",
            "Все учебники и раздаточные материалы собраны в одном облачном хранилище.",
            "Откройте по кнопке ниже — ссылка работает с телефона и компьютера.",
        ])
    elif website_url:
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


def build_first_lesson_payment_invite_text(
    student_name: str,
    requisites: dict,
    pricing_context: dict | None = None,
    speech_style: str | None = None,
) -> str:
    requisites_block = build_requisites_text(requisites or {}, pricing_context)
    intro = (
        f"💛 <b>Спасибо за первый урок, {html.quote(student_name)}!</b>"
        if student_name
        else "💛 <b>Спасибо за первый урок!</b>"
    )
    next_step = choose_form(
        speech_style,
        "Когда будет удобно, оплатите ближайшую неделю занятий — расписание и темп тогда сохранятся без пауз.",
        "Когда будет удобно, оплати ближайшую неделю занятий — расписание и темп тогда сохранятся без пауз.",
    )
    confirm = choose_form(
        speech_style,
        "После перевода нажмите <b>«Сообщить об оплате»</b>, и я её отмечу.",
        "После перевода нажми <b>«Сообщить об оплате»</b>, и я её отмечу.",
    )
    return (
        f"{intro}\n\n"
        f"Ниже — реквизиты на случай, если ещё не оплачивали.\n\n"
        f"{requisites_block}\n\n"
        f"{next_step}\n"
        f"{confirm}"
    )


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


def build_more_screen_text(role: str) -> str:
    if role == "parent":
        return (
            "👤 <b>Ещё</b>\n\n"
            "Здесь — профиль родителя и опасные действия."
        )
    return (
        "👤 <b>Ещё</b>\n\n"
        "Здесь — профиль, уведомления, тест уровня, заморозка и опасные действия."
    )


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
        "/help — эта справка\n\n"
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
        f"Сейчас бот говорит в режиме: <b>{html.quote(current_label)}</b>.\n"
        f"{html.quote(current_description)}\n\n"
        "Ниже можно переключить общий стиль формулировок для автоматических сообщений, шаблонных рассылок и ключевых экранов."
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


def build_parent_child_hub_text(child: dict) -> str:
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
        f"📚 Активные ДЗ: <b>{int(child.get('active_homework_count') or 0)}</b>",
        f"🎓 Баланс уроков: <b>{lesson_balance_label(child.get('lesson_balance'))}</b>",
        "",
        "Выберите ниже, что хотите посмотреть подробнее.",
    ])
    return "\n".join(lines)


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


def build_homework_empty_text(status: str) -> str:
    if status == "done":
        return (
            "✅ <b>Выполненные задания</b>\n\n"
            "Пока здесь пусто. Когда вы отметите задание как выполненное, оно появится в этом разделе."
        )
    return (
        "📚 <b>Активные задания</b>\n\n"
        "Сейчас активных домашних заданий нет. Когда преподаватель добавит новое, оно сразу появится здесь."
    )


def build_homework_text(items: list, status: str) -> str:
    if not items:
        return build_homework_empty_text(status)
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
        f"⏱ Scheduler: <b>{scheduler}</b>",
        f"🗓 Последний sync: <b>{html.quote(last_sync_label)}</b>",
        "",
        "Выберите раздел ниже.",
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
        freshness = student_freshness_badge(student.get("first_lesson_date"))
        lines.extend([
            "",
            f"<b>{index}. {html.quote(student['full_name'])}</b>",
            f"{lesson_format_icon(student.get('lesson_format'))} {lesson_format_label(student.get('lesson_format'))} · {html.quote(student.get('language') or '—')} {html.quote(student.get('level') or '—')} · {freshness}",
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
) -> str:
    reminders = reminder_status_label(student.get("lesson_reminders"))
    freshness = student_freshness_badge(student.get("first_lesson_date"))
    lines = [
        f"👤 <b>{html.quote(student['full_name'])}</b>",
        "",
        f"🏷 Статус: <b>{freshness}</b>",
        f"{lesson_format_icon(student.get('lesson_format'))} Формат: <b>{lesson_format_label(student.get('lesson_format'))}</b>",
        f"🗣 Обращение: <b>{speech_style_label(student.get('speech_style'))}</b>",
        f"🌍 Язык: <b>{html.quote(student.get('language') or '—')}</b>",
        f"📘 Уровень: <b>{html.quote(student.get('level') or '—')}</b>",
        f"🎓 Баланс: <b>{lesson_balance_label(balance)}</b>",
        f"📅 Ближайший урок: <b>{html.quote(format_datetime(next_lesson) if next_lesson else 'не назначен')}</b>",
        f"⏱ Длительность урока: <b>{lesson_duration_label(student.get('lesson_duration_minutes'))}</b>",
        f"🔔 Напоминания: <b>{html.quote(reminders)}</b>",
        f"🆔 Telegram ID: <code>{student['telegram_id']}</code>",
    ]
    pair_label = pair_title_label(pair)
    if pair_label:
        lines.extend([
            "",
            f"👥 <b>Пара:</b> {html.quote(pair_label)}",
            "Операционно ведётся через этот профиль: общий баланс, один темп, одно ДЗ.",
        ])
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
    return "\n".join([
        f"👥 <b>{html.quote(pair_title_label(pair) or 'Учебная пара')}</b>",
        "",
        "Участники:",
        *member_lines,
        "",
        f"Основной контакт: <b>{html.quote(pair.get('primary_student_name') or '—')}</b>",
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


def build_teacher_lesson_followup_text(lesson: dict) -> str:
    return "\n".join([
        "🧾 <b>Урок завершился</b>",
        "",
        f"👤 Ученик: <b>{html.quote(lesson.get('full_name') or '—')}</b>",
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
        f"👤 Ученик: <b>{html.quote(lesson.get('full_name') or '—')}</b>",
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


def build_admin_homework_description_prompt(
    student_name: str | None,
    recent_mentions: list,
    top_materials: list,
    latest_mention,
    has_homework_history: bool,
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

    if not has_homework_history:
        return ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT

    if not recent_mentions:
        lines = intro + [
            "📚 <b>По прошлым ДЗ</b>",
            "Статистика по учебникам или книгам пока не накоплена.",
            "",
            ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT,
        ]
        return "\n".join(lines)

    lines = intro + ["📚 <b>По прошлым ДЗ</b>"]
    for item in recent_mentions[:3]:
        progress = material_progress_label(item)
        date_value = (
            _item_value(item, "homework_created_at")
            or _item_value(item, "homework_deadline")
            or _item_value(item, "created_at")
        )
        summary_parts = [progress] if progress else []
        if date_value:
            summary_parts.append(format_date(date_value))
        suffix = f" · {' · '.join(summary_parts)}" if summary_parts else ""
        lines.append(f"• <b>{html.quote(str(_item_value(item, 'material_title') or '—'))}</b>{html.quote(suffix)}")

    if top_materials:
        lines.extend(["", "📈 <b>Чаще всего</b>"])
        for item in top_materials[:3]:
            count = int(_item_value(item, "mentions_count") or 0)
            lines.append(
                f"• <b>{html.quote(str(_item_value(item, 'material_title') or '—'))}</b> · {count} упомин."
            )

    hint_text = build_next_homework_hint(latest_mention, recent_mentions)
    if hint_text:
        lines.extend(["", "💡 <b>Подсказка</b>", html.quote(hint_text)])

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
        "💬 <b>Inbox</b>",
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


def build_parent_home_text_with_lights(parent_name: str, children: list[dict]) -> str:
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
