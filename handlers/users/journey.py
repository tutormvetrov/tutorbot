"""Onboarding v2: goal-setting FSM and journey dismiss callbacks."""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import back_to_menu_keyboard, cancel_fsm_keyboard
from states.registration import OnboardingGoal
from utils.db_api.postgresql import Database
from utils.ui_text import (
    GOAL_INVALID_TEXT,
    GOAL_PROMPT_FSM_TEXT,
    GOAL_SAVED_TEXT,
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda c: c.data == "goal:set", StateFilter("*"))
async def start_goal_set(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    user = await db.get_user(callback_query.from_user.id)
    if not user:
        await callback_query.answer("Сначала пройдите регистрацию через /start.", show_alert=True)
        return
    await state.clear()
    await state.set_state(OnboardingGoal.waiting_for_text)
    try:
        await callback_query.message.edit_text(GOAL_PROMPT_FSM_TEXT, reply_markup=cancel_fsm_keyboard)
    except Exception:
        await callback_query.message.answer(GOAL_PROMPT_FSM_TEXT, reply_markup=cancel_fsm_keyboard)
    await callback_query.answer()


@router.message(StateFilter(OnboardingGoal.waiting_for_text))
async def process_goal_text(message: types.Message, state: FSMContext, db: Database):
    raw = (message.text or "").strip()
    if len(raw) < 5 or len(raw) > 500:
        await message.answer(GOAL_INVALID_TEXT, reply_markup=cancel_fsm_keyboard)
        return
    user = await db.get_user(message.from_user.id)
    if not user:
        await state.clear()
        return

    await db.set_goal_text(message.from_user.id, raw)
    add_inbox_event = getattr(db, "add_inbox_event", None)
    if callable(add_inbox_event):
        try:
            await add_inbox_event("goal_set", {
                "telegram_id": message.from_user.id,
                "full_name": user.get("full_name") or str(message.from_user.id),
                "context": "onboarding",
                "message_preview": raw[:200],
            })
        except Exception:
            logger.warning("Failed to log goal_set inbox event", exc_info=True)

    await state.clear()
    await message.answer(GOAL_SAVED_TEXT, reply_markup=back_to_menu_keyboard)


@router.callback_query(lambda c: c.data == "goal:dismiss", StateFilter("*"))
async def dismiss_goal_prompt(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback_query.message.edit_text(
            "Хорошо, вернёмся к этому позже. Когда будете готовы — кнопка «🎯 Указать цель» "
            "появится снова на главном экране.",
            reply_markup=back_to_menu_keyboard,
        )
    except Exception:
        pass
    await callback_query.answer()
