"""Admin Pulse dashboard: traffic-light health screen + nudge/briefing callbacks."""
from __future__ import annotations

import logging

from aiogram import Router, types

from data import config
from keyboards.inline import (
    back_to_admin_keyboard,
    make_pulse_keyboard,
)
from utils.db_api.postgresql import Database
from utils.pulse_engine import (
    build_pulse_text,
    compute_all_health,
)

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ── Pulse screen ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "admin:pulse")
async def show_pulse(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Доступ запрещён", show_alert=True)
        return
    health_list = await compute_all_health(db)
    text = build_pulse_text(health_list)
    keyboard = make_pulse_keyboard(health_list)
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("pulse:student:"))
async def pulse_student_card(callback_query: types.CallbackQuery, db: Database):
    """Navigate from Pulse to student card."""
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Доступ запрещён", show_alert=True)
        return
    # Extract student_id and redirect to existing student card
    student_id_str = callback_query.data.replace("pulse:student:", "")
    try:
        student_id = int(student_id_str)
    except (ValueError, TypeError):
        await callback_query.answer("Ошибка: неверный ID ученика", show_alert=True)
        return

    # Reuse existing admin student card logic
    from handlers.users.admin_sections.students import _show_student_card
    if callable(getattr(_show_student_card, "__func__", _show_student_card)):
        try:
            await _show_student_card(callback_query, db, student_id)
        except Exception:
            await callback_query.answer(f"Ученик: {student_id}", show_alert=True)
    else:
        await callback_query.answer(f"Ученик: {student_id}", show_alert=True)


# ── Briefing callbacks ───────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "briefing:pulse")
async def briefing_to_pulse(callback_query: types.CallbackQuery, db: Database):
    """From morning briefing, navigate to full Pulse screen."""
    await show_pulse(callback_query, db)


@router.callback_query(lambda c: c.data and c.data.startswith("briefing:hw:"))
async def briefing_send_hw(callback_query: types.CallbackQuery, db: Database):
    """From morning briefing, go to HW creation for urgent student."""
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Доступ запрещён", show_alert=True)
        return
    student_id_str = callback_query.data.replace("briefing:hw:", "")
    try:
        student_id = int(student_id_str)
    except (ValueError, TypeError):
        await callback_query.answer("Ошибка", show_alert=True)
        return
    # Navigate to homework creation for this student
    await callback_query.answer(f"Перейдите к ДЗ для ученика {student_id}", show_alert=True)


# ── Nudge callbacks ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("nudge:hw:"))
async def nudge_send_hw(callback_query: types.CallbackQuery, db: Database):
    """Admin pressed 'Send HW' on a nudge."""
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Доступ запрещён", show_alert=True)
        return
    student_id_str = callback_query.data.replace("nudge:hw:", "")
    try:
        student_id = int(student_id_str)
    except (ValueError, TypeError):
        await callback_query.answer("Ошибка", show_alert=True)
        return
    # Tell admin to send HW - show alert with instruction
    user = await db.get_user(student_id)
    name = user.get("full_name") if user else str(student_id)
    await callback_query.answer(
        f"Отправьте ДЗ для {name} через меню «Учебный процесс»",
        show_alert=True,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("nudge:skip:"))
async def nudge_skip(callback_query: types.CallbackQuery, db: Database):
    """Admin pressed 'Skip' on a nudge."""
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Доступ запрещён", show_alert=True)
        return
    nudge_id_str = callback_query.data.replace("nudge:skip:", "")
    try:
        nudge_id = int(nudge_id_str)
    except (ValueError, TypeError):
        await callback_query.answer("Ошибка", show_alert=True)
        return
    await db.resolve_nudge(nudge_id, "skipped")
    try:
        await callback_query.message.edit_text(
            callback_query.message.text + "\n\n✅ Пропущено.",
            reply_markup=None,
        )
    except Exception:
        pass
    await callback_query.answer("Пропущено")


@router.callback_query(lambda c: c.data and c.data.startswith("nudge:nohw:"))
async def nudge_no_hw(callback_query: types.CallbackQuery, db: Database):
    """Admin pressed 'No HW needed' on a nudge."""
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Доступ запрещён", show_alert=True)
        return
    nudge_id_str = callback_query.data.replace("nudge:nohw:", "")
    try:
        nudge_id = int(nudge_id_str)
    except (ValueError, TypeError):
        await callback_query.answer("Ошибка", show_alert=True)
        return
    await db.resolve_nudge(nudge_id, "no_hw_needed")
    try:
        await callback_query.message.edit_text(
            callback_query.message.text + "\n\n✅ Урок без ДЗ. Закрыто.",
            reply_markup=None,
        )
    except Exception:
        pass
    await callback_query.answer("Закрыто")
