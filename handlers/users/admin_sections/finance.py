import asyncio
from datetime import datetime, timedelta

from aiogram import Router, types

from handlers.users.admin_sections.common import is_admin
from keyboards.inline import finance_keyboard
from utils.db_api.postgresql import Database
from utils.time import business_today
from utils.ui_text import build_finance_text

router = Router()


def _week_start() -> datetime:
    today = business_today()
    monday = today - timedelta(days=today.weekday())
    return datetime.combine(monday, datetime.min.time())


def _month_start() -> datetime:
    today = business_today()
    return datetime.combine(today.replace(day=1), datetime.min.time())


async def render_admin_finance(message, db: Database):
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
