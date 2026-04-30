from datetime import datetime

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from data import config
from utils.brand import brand_tone_label, get_brand_tone
from utils.db_api.postgresql import Database
from utils.google_calendar import load_last_sync_report
from utils.observability import load_ops_status, load_recent_runtime_events
from utils.ui_text import ADMIN_HEALTH_NO_ERRORS_TEXT

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(value)


def _format_job_line(label: str, job: dict | None, metric_keys: tuple[str, ...] = ()) -> str:
    if not job:
        return f"• {label}: <b>нет данных</b>"

    metric_labels = {
        "sent": "отправлено",
        "checked": "проверено",
        "unpaid": "без оплаты",
        "paid": "с оплатой",
        "completed": "завершено",
        "imported": "импортировано",
        "updated": "обновлено",
        "deleted": "удалено",
        "skipped": "пропущено",
        "sent_students": "учеников",
        "sent_items": "заданий",
        "failed_items": "ошибок",
        "due_items": "в очереди",
    }
    fragments = [f"• {label}: <b>{html.quote(str(job.get('status', 'unknown')))}</b>"]
    updated_at = _format_timestamp(job.get("updated_at"))
    if updated_at != "—":
        fragments.append(f"({updated_at})")

    metrics = []
    for key in metric_keys:
        if key in job:
            metrics.append(f"{metric_labels.get(key, key)}={html.quote(str(job[key]))}")
    if metrics:
        fragments.append("· " + ", ".join(metrics))
    return " ".join(fragments)


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _service_navigation_keyboard(active_view: str) -> InlineKeyboardMarkup:
    rows = [
        [
            _btn("🔄 Синхронизировать Calendar", "admin:sync:service"),
            _btn("📋 Отчёт синхронизации", "admin:calendar_report"),
        ],
        [_btn("◀️ К сервису", "admin:cat:service")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_health_text(student_count: int, report: dict, ops_status: dict, runtime_events: list[dict]) -> str:
    status = ops_status.get("status", "unknown")
    scheduler = ops_status.get("scheduler", "unknown")
    jobs = ops_status.get("jobs") or {}
    last_sync = report.get("synced_at_local") or _format_timestamp(ops_status.get("last_calendar_sync"))
    errors = [event for event in runtime_events if event.get("status") == "error"]

    lines = [
        "🏥 <b>Здоровье бота</b>",
        "",
        f"🤖 Статус: <b>{html.quote(str(status))}</b>",
        f"⏱ Scheduler: <b>{html.quote(str(scheduler))}</b>",
        f"👥 Активных учеников: <b>{student_count}</b>",
        f"🗓 Последний sync: <b>{html.quote(str(last_sync))}</b>",
        f"📥 Импортировано: <b>{report.get('imported', 0)}</b>",
        f"♻️ Обновлено: <b>{report.get('updated', 0)}</b>",
        f"🗑 Удалено: <b>{report.get('deleted', 0)}</b>",
        f"⏭ Пропущено: <b>{report.get('skipped', 0)}</b>",
        "",
        "🔔 <b>Планировщик напоминаний</b>",
        _format_job_line("Уроки", jobs.get("lesson_reminder"), ("sent", "checked")),
        _format_job_line("Фоллоу-ап после урока", jobs.get("teacher_lesson_followup"), ("sent", "checked")),
        _format_job_line("Закладки перед уроком", jobs.get("teacher_bookmark_reminder"), ("sent", "checked")),
        _format_job_line("Домашка", jobs.get("homework_reminder"), ("sent",)),
        _format_job_line(
            "Отложенная домашка",
            jobs.get("queued_homework_delivery"),
            ("sent_students", "sent_items", "failed_items", "due_items"),
        ),
        _format_job_line("Оплата (утро)", jobs.get("payment_reminder_morning"), ("unpaid", "paid")),
        _format_job_line("Оплата (вечер)", jobs.get("payment_reminder_evening"), ("unpaid", "paid")),
        _format_job_line(
            "Учебный план",
            jobs.get("study_plan_weekly_digest"),
            ("sent_students", "sent_parents", "checked_students", "checked_parents"),
        ),
    ]

    if errors:
        lines.append("")
        lines.append("⚠️ <b>Последние ошибки jobs:</b>")
        for event in errors[-5:]:
            lines.append(f"• {html.quote(event.get('event_type', 'unknown'))}: {html.quote(event.get('status', 'unknown'))}")
    else:
        lines.append("")
        lines.append(ADMIN_HEALTH_NO_ERRORS_TEXT)

    return "\n".join(lines)


def _format_service_context_text(ops_status: dict, runtime_events: list[dict]) -> str:
    scheduler = ops_status.get("scheduler", "unknown")
    errors = [event for event in runtime_events if event.get("status") == "error"]
    tone = brand_tone_label(get_brand_tone())

    lines = [
        "🧭 <b>Контекст и проект</b>",
        "",
        f"🎨 Тональность бренда: <b>{html.quote(tone)}</b>",
        f"⏱ Scheduler: <b>{html.quote(str(scheduler))}</b>",
        "",
        "Здесь собраны рабочие настройки и заметки по проекту.",
        "Тональность меняется отдельной кнопкой, а заметки открываются в этом же сервисном разделе.",
    ]
    if errors:
        lines.extend([
            "",
            f"⚠️ Последних runtime-ошибок: <b>{len(errors)}</b>",
        ])
    return "\n".join(lines)


async def _render_monitoring_screen(callback_query: types.CallbackQuery, db: Database):
    students = await db.get_all_students()
    report = load_last_sync_report()
    ops_status = load_ops_status()
    runtime_events = load_recent_runtime_events(limit=30)

    await callback_query.message.edit_text(
        _format_health_text(len(students), report, ops_status, runtime_events),
        reply_markup=_service_navigation_keyboard("monitoring"),
    )


async def _render_context_screen(callback_query: types.CallbackQuery, db: Database):
    ops_status = load_ops_status()
    runtime_events = load_recent_runtime_events(limit=30)

    await callback_query.message.edit_text(
        _format_service_context_text(ops_status, runtime_events),
        reply_markup=_service_navigation_keyboard("context"),
    )


@router.callback_query(lambda c: c.data == "admin:health", StateFilter("*"))
async def admin_health(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await _render_monitoring_screen(callback_query, db)
    await callback_query.answer()
