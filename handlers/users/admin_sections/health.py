import asyncio
import json
import logging
import os
import re
import subprocess
from datetime import datetime

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from data import config
from utils.brand import brand_tone_label, get_brand_tone
from utils.db_api.postgresql import Database
from utils.google_calendar import load_last_sync_report
from utils.observability import (
    load_ops_status,
    load_recent_runtime_events,
    load_touches_runtime,
    set_touches_runtime,
)
from utils.ui_text import ADMIN_HEALTH_NO_ERRORS_TEXT

logger = logging.getLogger(__name__)

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
        f"⏱ Планировщик: <b>{html.quote(str(scheduler))}</b>",
        f"👥 Активных учеников: <b>{student_count}</b>",
        f"🗓 Последняя синхронизация: <b>{html.quote(str(last_sync))}</b>",
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
        f"⏱ Планировщик: <b>{html.quote(str(scheduler))}</b>",
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


# ─── Touches: pause/resume + audit ───────────────────────────────────────────

def _touches_settings_keyboard(paused: bool) -> InlineKeyboardMarkup:
    toggle_label = "▶️ Возобновить рассылку" if paused else "⏸ Поставить рассылку на паузу"
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(toggle_label, "admin:touches:toggle")],
        [_btn("📜 Последние касания", "admin:touches:last")],
        [_btn("◀️ К сервису", "admin:cat:service")],
    ])


def _format_touches_settings_text(state: dict) -> str:
    paused = bool(state.get("paused"))
    lines = [
        "💬 <b>Касания между уроками</b>",
        "",
        f"Статус: <b>{'⏸ на паузе' if paused else '🟢 активны'}</b>",
        f"Расписание: ежедневно в {config.TOUCHES_RUN_HOUR:02d}:{config.TOUCHES_RUN_MINUTE:02d} {config.BUSINESS_TIMEZONE_LABEL}",
        "Лимиты: не чаще 1 раза в день и 1 раза в неделю на ученика.",
    ]
    if paused:
        updated_at = _format_timestamp(state.get("updated_at"))
        lines.append("")
        lines.append(f"⏸ Поставлено на паузу: {updated_at}")
        reason = state.get("reason")
        if reason:
            lines.append(f"Причина: {html.quote(str(reason))}")
    return "\n".join(lines)


@router.callback_query(lambda c: c.data == "admin:touches:settings", StateFilter("*"))
async def admin_touches_settings(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    state = load_touches_runtime()
    await callback_query.message.edit_text(
        _format_touches_settings_text(state),
        reply_markup=_touches_settings_keyboard(bool(state.get("paused"))),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:touches:toggle", StateFilter("*"))
async def admin_touches_toggle(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    state = load_touches_runtime()
    new_paused = not bool(state.get("paused"))
    new_state = set_touches_runtime(paused=new_paused, by=callback_query.from_user.id)
    await callback_query.message.edit_text(
        _format_touches_settings_text(new_state),
        reply_markup=_touches_settings_keyboard(new_paused),
    )
    await callback_query.answer("⏸ Поставлено на паузу" if new_paused else "▶️ Возобновлено")


@router.callback_query(lambda c: c.data == "admin:touches:last", StateFilter("*"))
async def admin_touches_last(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    rows = await db.get_last_touches(limit=20)
    if not rows:
        text = "📭 Касаний ещё не было."
    else:
        lines = ["💬 <b>Последние 20 касаний</b>", ""]
        for r in rows:
            ts = _format_timestamp(r.get("sent_at"))
            who = html.quote(r.get("preferred_name") or r.get("full_name") or str(r.get("student_id")))
            ttype = html.quote(str(r.get("template_type") or "—"))
            tidx = r.get("template_index")
            tidx_s = f"#{tidx}" if tidx is not None else "—"
            lines.append(f"• {ts} — {who} — {ttype} {tidx_s}")
        text = "\n".join(lines)
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [_btn("◀️ К настройкам касаний", "admin:touches:settings")],
        ]),
    )
    await callback_query.answer()


# ─── Bot restart ─────────────────────────────────────────────────────────────

_restart_confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        _btn("✅ Да, перезапустить", "admin:restart:confirm"),
        _btn("❌ Отмена", "admin:cat:service"),
    ],
])


@router.callback_query(lambda c: c.data == "admin:restart", StateFilter("*"))
async def admin_restart_prompt(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        "🔄 <b>Перезапуск бота</b>\n\n"
        "Бот будет недоступен несколько секунд.\n"
        "Вы уверены?",
        reply_markup=_restart_confirm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:restart:confirm", StateFilter("*"))
async def admin_restart_confirm(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await callback_query.message.edit_text("🔄 Перезапускаюсь…")
    await callback_query.answer()

    pending_file = config.PROJECT_ROOT / "data" / "pending_restart_msg.json"
    try:
        pending_file.write_text(
            json.dumps({
                "chat_id": callback_query.message.chat.id,
                "message_id": callback_query.message.message_id,
            }),
            encoding="utf-8",
        )
        logger.info("pending_restart_msg.json сохранён: chat=%s msg=%s",
                    callback_query.message.chat.id, callback_query.message.message_id)
    except Exception:
        logger.exception("Не удалось сохранить pending_restart_msg.json")

    async def _do_restart():
        await asyncio.sleep(1)
        try:
            service_name = os.getenv("TUTORBOT_SERVICE_NAME", "tutorbot").strip() or "tutorbot"
            if not re.fullmatch(r"[a-zA-Z0-9_\-]+", service_name):
                logger.error("Недопустимое имя сервиса TUTORBOT_SERVICE_NAME: %r", service_name)
                return
            subprocess.Popen(
                ["sudo", "systemctl", "restart", service_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.exception("Не удалось перезапустить бота")

    asyncio.create_task(_do_restart())


# ─── Achievement backfill ─────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin:service:backfill_achievements", StateFilter("*"))
async def admin_backfill_achievements_prompt(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        "🔄 <b>Пересчитать достижения</b>\n\n"
        "Проверить всех учеников и выдать заслуженные достижения задним числом.\n"
        "Это может занять пару минут. Продолжить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, пересчитать", callback_data="admin:service:backfill_achievements:confirm")],
            [InlineKeyboardButton(text="◀️ К сервису", callback_data="admin:cat:service")],
        ]),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:service:backfill_achievements:confirm", StateFilter("*"))
async def admin_backfill_achievements_run(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await callback_query.message.edit_text("🔄 Пересчитываю достижения…")

    from utils.achievements import ACHIEVEMENTS
    from utils.pulse_engine import _compute_streak_weeks

    students = await db.get_all_pulse_data()
    total_granted = 0
    students_affected = set()
    now = datetime.now()

    for row in (students or []):
        student_id = row["telegram_id"]
        total_lessons = int(row.get("total_lessons") or 0)
        first_lesson = row.get("first_lesson_date")
        last_lesson = row.get("last_lesson_date")

        streak = _compute_streak_weeks(first_lesson, last_lesson, total_lessons, now)
        tenure_weeks = max(0, (now - first_lesson).days // 7) if first_lesson else 0
        goal_text = row.get("goal_text")

        progress = await db.get_student_progress(student_id)
        plan_total = int(progress.get("plan_total") or 0)
        plan_done = int(progress.get("plan_done") or 0)
        hw_months = await db.get_student_hw_perfect_months(student_id)

        metrics = {
            "total_lessons": total_lessons,
            "streak_weeks": streak,
            "tenure_weeks": tenure_weeks,
            "goal_text": goal_text,
            "plan_total": plan_total,
            "plan_done": plan_done,
            "hw_perfect_months": len(hw_months) if hw_months else 0,
        }

        for achievement in ACHIEVEMENTS:
            if achievement["check"](metrics):
                unlocked_at = None
                key = achievement["key"]
                if key == "first_lesson" and first_lesson:
                    unlocked_at = first_lesson
                elif key.startswith("lessons_"):
                    n = int(key.split("_")[1])
                    unlocked_at = await db.get_nth_lesson_date(student_id, n)
                elif key.startswith("tenure_"):
                    w = int(key.replace("tenure_", "").replace("w", ""))
                    if first_lesson:
                        from datetime import timedelta
                        unlocked_at = first_lesson + timedelta(weeks=w)
                was_new = await db.grant_achievement(
                    student_id, key,
                    unlocked_at=unlocked_at,
                    notified=True,
                )
                if was_new:
                    total_granted += 1
                    students_affected.add(student_id)

    await callback_query.message.edit_text(
        f"✅ Пересчитано. Выдано {total_granted} достижений для {len(students_affected)} учеников.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К сервису", callback_data="admin:cat:service")],
        ]),
    )
