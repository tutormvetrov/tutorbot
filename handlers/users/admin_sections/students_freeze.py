"""Ручная заморозка ученика админом.

Сценарий: новый ученик зарегистрировался, но реально начнёт заниматься через
несколько недель. Админ ставит ему `frozen_until` — все автоматические
рассылки (онбординг, напоминания об оплате, тачи между уроками) фильтруют
его до указанной даты.

Заморозка флагом ученика существует **параллельно** с заявочным механизмом
заморозки отдельных уроков (`lessons.status='frozen'`, экран
`admin:freezes`). Эти механизмы не конфликтуют, но при наличии
запланированных `active`-уроков в периоде заморозки бот предложит
перевести их в `frozen` одной кнопкой.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, types

from handlers.users.admin_sections._students_helpers import (
    _render_admin_student_actions,
)
from handlers.users.admin_sections.common import is_admin, parse_admin_callback, q
from keyboards.admin_students import (
    make_admin_student_freeze_lessons_prompt_keyboard,
    make_admin_student_freeze_period_keyboard,
)
from keyboards.inline import back_to_admin_keyboard
from utils.db_api.postgresql import Database
from utils.db_api.users import FREEZE_FOREVER_SENTINEL


router = Router()


PERIOD_LABELS = {
    "7d": "неделю",
    "14d": "2 недели",
    "30d": "месяц",
    "90d": "3 месяца",
    "forever": "бессрочно",
}


def _resolve_freeze_until(period: str) -> datetime | None:
    """`None` означает «бессрочно» (sentinel 2100-01-01)."""
    if period == "forever":
        return None
    days_map = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}
    days = days_map.get(period)
    if days is None:
        return None
    return datetime.utcnow() + timedelta(days=days)


@router.callback_query(lambda c: c.data and c.data.startswith("admin:student_freeze:"))
async def admin_student_freeze_open(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0

    student = await db.get_user(student_id)
    if not student or student.get("role") != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return
    name = q(student["full_name"])

    await callback_query.message.edit_text(
        f"❄️ <b>Заморозить {name}?</b>\n\n"
        "Бот перестанет слать ученику автоматические сообщения "
        "(онбординг, напоминания об оплате, тачи между уроками) "
        "до выбранной даты.\n\n"
        "Выберите срок:",
        reply_markup=make_admin_student_freeze_period_keyboard(student_id, page),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:student_freeze_set:"))
async def admin_student_freeze_set(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    period = parts[4] if len(parts) > 4 else "7d"
    if period not in PERIOD_LABELS:
        await callback_query.answer("Неизвестный период.", show_alert=True)
        return

    until_dt = _resolve_freeze_until(period)
    # Для проверки наличия уроков используем фактическую границу заморозки.
    boundary = until_dt if until_dt is not None else FREEZE_FOREVER_SENTINEL

    # Если в периоде заморозки уже есть активные уроки — спросим админа,
    # переводить ли их в `frozen`.
    upcoming = await db.get_active_lessons_in_freeze_period(student_id, boundary)
    if upcoming:
        student = await db.get_user(student_id)
        name = q(student["full_name"]) if student else str(student_id)
        await callback_query.message.edit_text(
            f"❄️ <b>{name}</b> — заморозка на {PERIOD_LABELS[period]}.\n\n"
            f"В этот период запланировано <b>{len(upcoming)}</b> "
            f"урок(ов). Перевести их в статус «frozen» (тогда они не "
            f"попадут в напоминания и расписание)?\n\n"
            "Если оставить как есть — уроки останутся `active`, а бот "
            "просто не будет беспокоить ученика напоминаниями.",
            reply_markup=make_admin_student_freeze_lessons_prompt_keyboard(
                student_id, page, period, len(upcoming)
            ),
        )
        await callback_query.answer()
        return

    # Уроков в периоде нет — сразу применяем заморозку.
    await db.freeze_student(student_id, until_dt)
    await _render_admin_student_actions(callback_query.message, db, student_id, page)
    await callback_query.answer(
        f"❄️ Заморожен на {PERIOD_LABELS[period]}.",
        show_alert=False,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:student_freeze_apply:"))
async def admin_student_freeze_apply(callback_query: types.CallbackQuery, db: Database):
    """Применить заморозку после выбора, что делать с активными уроками."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    # callback: admin:student_freeze_apply:<tg_id>:<page>:<period>:<yes|no>
    raw = callback_query.data.split(":")
    if len(raw) < 6:
        await callback_query.answer("Битая команда.", show_alert=True)
        return
    student_id = int(raw[2])
    page = int(raw[3])
    period = raw[4]
    apply_to_lessons = raw[5] == "yes"
    if period not in PERIOD_LABELS:
        await callback_query.answer("Неизвестный период.", show_alert=True)
        return

    until_dt = _resolve_freeze_until(period)
    boundary = until_dt if until_dt is not None else FREEZE_FOREVER_SENTINEL

    await db.freeze_student(student_id, until_dt)
    moved = 0
    if apply_to_lessons:
        moved = await db.freeze_active_lessons(student_id, boundary)

    await _render_admin_student_actions(callback_query.message, db, student_id, page)
    if apply_to_lessons:
        await callback_query.answer(
            f"❄️ Заморожен на {PERIOD_LABELS[period]}. Переведено уроков: {moved}.",
            show_alert=False,
        )
    else:
        await callback_query.answer(
            f"❄️ Заморожен на {PERIOD_LABELS[period]}. Уроки оставлены без изменений.",
            show_alert=False,
        )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:student_unfreeze:"))
async def admin_student_unfreeze(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0

    await db.unfreeze_student(student_id)
    await _render_admin_student_actions(callback_query.message, db, student_id, page)
    await callback_query.answer("☀️ Разморожен.")
