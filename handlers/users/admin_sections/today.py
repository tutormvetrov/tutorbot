"""
Admin «🎯 Сегодня» dashboard handler (Stage 2).

Handles:
  admin:today           — main «Сегодня» screen
  admin:today:lessons   — today's lesson list
  admin:today:unpaid    — students with zero balance (send requisites)
  admin:today:missing_hw — students missing homework before tomorrow's lesson
  admin:cat:education:lessons  — sub-screen for lesson actions
  admin:finance:payments       — sub-screen for payment actions
  admin:cat:education:homework — sub-screen for homework actions
"""

from datetime import datetime, timedelta

from aiogram import Router, types
from aiogram.filters import StateFilter

from data import config
from data.config import load_teacher_info
from keyboards.inline import (
    make_admin_today_keyboard,
    make_back_button_keyboard,
)
from utils.db_api.postgresql import Database
from utils.time import business_naive_now
from utils.ui_text import build_admin_today_text

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


def _today_window() -> tuple[datetime, datetime]:
    """Return (today_start, tomorrow_start) in the bot's business timezone."""
    now = business_naive_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return today_start, tomorrow_start


# ─── «🎯 Сегодня» main screen ────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin:today", StateFilter("*"))
async def admin_today(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    today_start, tomorrow_start = _today_window()
    snapshot = await db.get_admin_today_snapshot(today_start, tomorrow_start)
    today_date = today_start.date()

    await callback_query.message.edit_text(
        build_admin_today_text(snapshot, today_date),
        reply_markup=make_admin_today_keyboard(snapshot),
    )
    await callback_query.answer()


# ─── «Сегодня» sub-screens ───────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin:today:lessons", StateFilter("*"))
async def admin_today_lessons(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    today_start, tomorrow_start = _today_window()
    lessons_raw = await db.get_lessons_in_window(today_start, tomorrow_start)
    back_kb = make_back_button_keyboard("◀️ К Сегодня", "admin:today")

    if not lessons_raw:
        await callback_query.message.edit_text(
            "📅 <b>Уроки сегодня</b>\n\nУроков на сегодня не запланировано.",
            reply_markup=back_kb,
        )
        await callback_query.answer()
        return

    student_ids = [row["student_id"] for row in lessons_raw]
    users_rows = await db._get_users_by_ids(student_ids)
    name_map = {r["telegram_id"]: r.get("full_name") or str(r["telegram_id"]) for r in users_rows}
    format_map = {r["telegram_id"]: (r.get("lesson_format") or "online").strip().lower() for r in users_rows}

    lines = [f"📅 <b>Уроки сегодня</b> ({len(lessons_raw)} шт.)", ""]
    for row in lessons_raw:
        lesson_date: datetime | None = row.get("lesson_date")
        time_str = lesson_date.strftime("%H:%M") if lesson_date else "—"
        sid = row["student_id"]
        fmt = format_map.get(sid, "online")
        fmt_label = "очно" if fmt == "offline" else "онлайн"
        name = name_map.get(sid, str(sid))
        lines.append(f"• {time_str} · <b>{name}</b> ({fmt_label})")

    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:today:unpaid", StateFilter("*"))
async def admin_today_unpaid(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    students = await db.get_students_with_balances()
    unpaid = [s for s in (students or []) if int(s.get("lesson_balance") or 0) == 0]
    back_kb = make_back_button_keyboard("◀️ К Сегодня", "admin:today")

    if not unpaid:
        await callback_query.message.edit_text(
            "💰 <b>Реквизиты</b>\n\nВсе ученики имеют уроки на балансе. Отправлять реквизиты не нужно.",
            reply_markup=back_kb,
        )
        await callback_query.answer()
        return

    teacher_info = load_teacher_info()
    contacts = teacher_info.get("contacts", {}) if teacher_info else {}
    payment_details = contacts.get("payment_details") or contacts.get("requisites") or ""

    lines = [f"💰 <b>Кому отправить реквизиты</b> ({len(unpaid)} уч.)", ""]
    for s in unpaid:
        lines.append(f"• <b>{s['full_name']}</b> — баланс: 0 уроков")
    if payment_details:
        lines.extend(["", f"💳 Реквизиты: <code>{payment_details}</code>"])

    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:today:missing_hw", StateFilter("*"))
async def admin_today_missing_hw(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    missing = await db.get_lessons_missing_homework()
    back_kb = make_back_button_keyboard("◀️ К Сегодня", "admin:today")

    if not missing:
        await callback_query.message.edit_text(
            "📚 <b>ДЗ перед завтрашними уроками</b>\n\nВсё в порядке — у всех учеников есть домашнее задание.",
            reply_markup=back_kb,
        )
        await callback_query.answer()
        return

    lines = [f"📚 <b>Кому задать ДЗ</b> ({len(missing)} уч.)", ""]
    for row in missing:
        lesson_date: datetime | None = row.get("lesson_date")
        time_str = lesson_date.strftime("%d.%m %H:%M") if lesson_date else "—"
        lines.append(f"• <b>{row['full_name']}</b> — урок {time_str}")

    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb,
    )
    await callback_query.answer()


# ─── Education sub-screens (verb-style routing) ───────────────────────────────

@router.callback_query(lambda c: c.data == "admin:cat:education:lessons", StateFilter("*"))
async def admin_education_lessons(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    def _btn(text: str, cb: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=cb)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("➕ Добавить занятие", "admin:add_lesson:education")],
        [_btn("🗑 Удалить занятие", "admin:manage_lessons")],
        [_btn("◀️ К учебному процессу", "admin:cat:education")],
    ])
    await callback_query.message.edit_text(
        "📅 <b>Уроки</b>\n\nВыберите действие:",
        reply_markup=kb,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:finance:payments", StateFilter("*"))
async def admin_finance_payments(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    def _btn(text: str, cb: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=cb)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("💳 Добавить оплату", "admin:add_payment:finance")],
        [_btn("◀️ К финансам", "admin:finance")],
    ])
    await callback_query.message.edit_text(
        "💰 <b>Оплаты</b>\n\nВыберите действие:",
        reply_markup=kb,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:cat:education:homework", StateFilter("*"))
async def admin_education_homework(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    def _btn(text: str, cb: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=cb)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📚 Задать ДЗ", "admin:add_homework:education")],
        [_btn("📋 Активные ДЗ", "admin:all_homework")],
        [_btn("◀️ К учебному процессу", "admin:cat:education")],
    ])
    await callback_query.message.edit_text(
        "📚 <b>Домашние задания</b>\n\nВыберите действие:",
        reply_markup=kb,
    )
    await callback_query.answer()
