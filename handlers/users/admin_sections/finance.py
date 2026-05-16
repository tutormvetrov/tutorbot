import asyncio
from datetime import datetime, timedelta

from aiogram import Router, types

from handlers.users.admin_sections.common import is_admin
from keyboards.inline import (
    finance_keyboard,
    make_admin_inbox_item_keyboard,
    make_finance_balances_keyboard,
    make_finance_payment_inbox_keyboard,
)
from utils.db_api.postgresql import Database
from utils.telegram_actions import with_chat_action
from utils.time import business_today
from utils.ui_text import build_admin_inbox_item_text, build_admin_inbox_text, build_finance_text

router = Router()


def _payload_dict(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        import json
        try:
            return json.loads(payload)
        except Exception:
            return {}
    return {}


def _week_start() -> datetime:
    today = business_today()
    monday = today - timedelta(days=today.weekday())
    return datetime.combine(monday, datetime.min.time())


def _month_start() -> datetime:
    today = business_today()
    return datetime.combine(today.replace(day=1), datetime.min.time())


async def render_admin_finance(message, db: Database):
    async with with_chat_action(message, "typing"):
        income_week, income_month, discipline_raw, tariff_raw, forecast_raw = await asyncio.gather(
            db.get_income_period(_week_start()),
            db.get_income_period(_month_start()),
            db.get_payment_discipline(),
            db.get_tariff_stats(),
            db.get_forecast_data(),
        )
    discipline = list(discipline_raw or [])
    tariff_stats = list(tariff_raw or [])
    forecast_data = list(forecast_raw or [])

    total_lessons_28d = sum(r.get("lessons_28d", 0) for r in forecast_data)
    total_lost_28d = sum(r.get("lost_28d", 0) for r in forecast_data)
    lost_pct = (total_lost_28d / total_lessons_28d * 100) if total_lessons_28d else 0
    adjustment = 1 - lost_pct / 100

    forecast_week = sum(
        float(r.get("rate_amount", 0)) * r.get("lessons_per_week", 1)
        for r in forecast_data
    ) * adjustment
    forecast_month = forecast_week * 4

    text = build_finance_text(
        income_week=income_week,
        income_month=income_month,
        discipline=discipline,
        forecast_week=forecast_week,
        forecast_month=forecast_month,
        lost_pct=lost_pct,
        tariff_stats=tariff_stats,
    )
    await message.edit_text(text, reply_markup=finance_keyboard)


@router.callback_query(lambda c: c.data == "admin:finance")
async def admin_finance(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await render_admin_finance(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:finance:payment_inbox")
async def admin_finance_payment_inbox(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    async with with_chat_action(callback_query, "typing"):
        events = list(await db.get_unread_inbox(limit=30) or [])
        payment_events = [
            event
            for event in events
            if _payload_dict(event.get("payload")).get("context") == "payment"
        ]
    await callback_query.message.edit_text(
        build_admin_inbox_text(payment_events).replace("💬 <b>Входящие</b>", "📥 <b>Входящие оплаты</b>", 1),
        reply_markup=make_finance_payment_inbox_keyboard(payment_events),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:finance:inbox:item:"))
async def admin_finance_inbox_item(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    try:
        event_id = int(callback_query.data.split(":")[4])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка: неверный формат.", show_alert=True)
        return

    async with with_chat_action(callback_query, "typing"):
        event = await db.get_inbox_event(event_id)
    if not event:
        await callback_query.answer("Событие не найдено.", show_alert=True)
        return

    payload = _payload_dict(event.get("payload"))
    await callback_query.message.edit_text(
        build_admin_inbox_item_text(event),
        reply_markup=make_admin_inbox_item_keyboard(
            event_id,
            event.get("kind") or "",
            context=payload.get("context"),
            student_id=payload.get("student_id"),
            back_callback="admin:finance:payment_inbox",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:finance:balances")
async def admin_finance_balances(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    async with with_chat_action(callback_query, "typing"):
        students = sorted(
            list(await db.get_students_with_balances() or []),
            key=lambda s: (int(s.get("lesson_balance") or 0), s.get("full_name") or ""),
        )
    lines = ["📊 <b>Балансы учеников</b>", ""]
    if students:
        lines.append("Сначала показаны те, у кого меньше уроков.")
    else:
        lines.append("Активных учеников нет.")
    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=make_finance_balances_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:finance:unpaid")
async def admin_finance_unpaid(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    async with with_chat_action(callback_query, "typing"):
        students = [
            s
            for s in list(await db.get_students_with_balances() or [])
            if int(s.get("lesson_balance") or 0) <= 0
        ]
    students.sort(key=lambda s: (int(s.get("lesson_balance") or 0), s.get("full_name") or ""))
    lines = [f"⚠️ <b>Нулевой баланс</b> ({len(students)})", ""]
    if students:
        lines.append("Выберите ученика, чтобы добавить оплату, обнулить баланс или перенести долг.")
    else:
        lines.append("Нет учеников с нулевым или отрицательным балансом.")
    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=make_finance_balances_keyboard(students),
    )
    await callback_query.answer()
