"""Onboarding v2: goal-setting FSM, pair goal, and journey dismiss callbacks."""
from __future__ import annotations

import html as html_lib
import logging

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.inline import back_to_menu_keyboard, cancel_fsm_keyboard
from states.registration import OnboardingGoal
from utils.db_api.postgresql import Database
from utils.ui_text import (
    GOAL_INVALID_TEXT,
    GOAL_PROMPT_FSM_TEXT,
    GOAL_SAVED_TEXT,
    PAIR_GOAL_INVALID_TEXT,
    PAIR_GOAL_PROMPT_FSM_TEXT,
    PAIR_GOAL_PROMPT_TEXT,
    PAIR_GOAL_SAVED_TEXT,
)


class PairGoal(StatesGroup):
    waiting_for_text = State()


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


# ─── Pair shared goal ────────────────────────────────────────────────────────

async def _resolve_pair_for_user(db: Database, user_id: int) -> dict | None:
    get_pair = getattr(db, "get_student_pair_for_student", None)
    if not callable(get_pair):
        return None
    return await get_pair(user_id)


@router.callback_query(lambda c: c.data == "pair_goal:open", StateFilter("*"))
async def open_pair_goal(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    pair = await _resolve_pair_for_user(db, callback_query.from_user.id)
    if not pair:
        await callback_query.answer("Эта функция доступна только участникам пары.", show_alert=True)
        return
    await state.clear()
    goal = (pair.get("shared_goal_text") or "").strip()
    if goal:
        text = (
            "🎯 <b>Общая цель пары</b>\n\n"
            f"«{html_lib.escape(goal)}»\n\n"
            "Можно изменить или оставить как есть."
        )
    else:
        text = PAIR_GOAL_PROMPT_TEXT
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Поставить / изменить цель", callback_data="pair_goal:set")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")],
    ])
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback_query.message.answer(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "pair_goal:set", StateFilter("*"))
async def start_pair_goal_set(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    pair = await _resolve_pair_for_user(db, callback_query.from_user.id)
    if not pair:
        await callback_query.answer("Эта функция доступна только участникам пары.", show_alert=True)
        return
    await state.clear()
    await state.set_state(PairGoal.waiting_for_text)
    await state.update_data(pair_id=int(pair["id"]))
    try:
        await callback_query.message.edit_text(PAIR_GOAL_PROMPT_FSM_TEXT, reply_markup=cancel_fsm_keyboard)
    except Exception:
        await callback_query.message.answer(PAIR_GOAL_PROMPT_FSM_TEXT, reply_markup=cancel_fsm_keyboard)
    await callback_query.answer()


@router.message(StateFilter(PairGoal.waiting_for_text))
async def process_pair_goal_text(message: types.Message, state: FSMContext, db: Database):
    raw = (message.text or "").strip()
    if len(raw) < 5 or len(raw) > 500:
        await message.answer(PAIR_GOAL_INVALID_TEXT, reply_markup=cancel_fsm_keyboard)
        return
    data = await state.get_data()
    pair_id = int(data.get("pair_id") or 0)
    if not pair_id:
        await state.clear()
        await message.answer("⚠️ Не удалось определить пару. Откройте «🎯 Наша цель» снова.")
        return

    set_goal = getattr(db, "set_pair_goal", None)
    if not callable(set_goal):
        await state.clear()
        await message.answer("⚠️ Функция временно недоступна.")
        return
    ok = await set_goal(pair_id, raw)
    if not ok:
        await state.clear()
        await message.answer("⚠️ Пара не найдена или неактивна.")
        return

    add_inbox_event = getattr(db, "add_inbox_event", None)
    if callable(add_inbox_event):
        try:
            await add_inbox_event("pair_goal_set", {
                "telegram_id": message.from_user.id,
                "full_name": message.from_user.full_name or str(message.from_user.id),
                "context": "pair_goal",
                "pair_id": pair_id,
                "message_preview": raw[:200],
            })
        except Exception:
            pass

    await state.clear()
    await message.answer(PAIR_GOAL_SAVED_TEXT, reply_markup=back_to_menu_keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("pair_goal:inherit:"), StateFilter("*"))
async def inherit_partner_goal(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    parts = (callback_query.data or "").split(":")
    try:
        pair_id = int(parts[2])
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    user_pair = await _resolve_pair_for_user(db, callback_query.from_user.id)
    if not user_pair or int(user_pair["id"]) != pair_id:
        await callback_query.answer("Эта кнопка не для вашей пары.", show_alert=True)
        return

    primary_id = int(user_pair["primary_student_id"])
    primary_user = await db.get_user(primary_id)
    primary_goal = (primary_user.get("goal_text") or "").strip() if primary_user else ""
    if not primary_goal:
        await callback_query.answer("Цель партнёра больше не доступна.", show_alert=True)
        return

    set_goal = getattr(db, "set_pair_goal", None)
    if not callable(set_goal):
        await callback_query.answer("Функция временно недоступна.", show_alert=True)
        return
    ok = await set_goal(pair_id, primary_goal)
    if not ok:
        await callback_query.answer("Не удалось сохранить.", show_alert=True)
        return
    await state.clear()
    await callback_query.message.edit_text(PAIR_GOAL_SAVED_TEXT, reply_markup=back_to_menu_keyboard)
    await callback_query.answer("Цель сохранена.")
