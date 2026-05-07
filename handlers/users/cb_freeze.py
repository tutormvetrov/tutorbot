"""Freeze feature callbacks."""
import logging

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from handlers.users._cb_helpers import (
    _block_preview_action,
    _get_learning_student_id,
)
from keyboards.inline import (
    back_to_menu_keyboard,
    FREEZE_REASON_LABELS,
    make_freeze_confirm_keyboard,
)
from states.registration import FreezeConfirm
from utils.db_api.postgresql import Database
from utils.ui_text import (
    build_action_result_text,
    build_freeze_confirm_text,
    build_freeze_success_text,
)

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data.startswith('freeze:'))
async def process_freeze_reason(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if await _block_preview_action(callback_query, db, clear_state=state):
        return

    get_user = getattr(db, "get_user", None)
    user = await get_user(callback_query.from_user.id) if callable(get_user) else None
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Заморозка доступна ученикам.", show_alert=True)
        return

    reason = callback_query.data.split(':')[1]
    label = FREEZE_REASON_LABELS.get(reason, reason)
    learning_user_id = await _get_learning_student_id(db, callback_query.from_user.id)
    active_lessons = await db.get_active_lessons(learning_user_id)
    active_count = len(active_lessons)

    if not active_count:
        await callback_query.message.edit_text(
            build_action_result_text(
                "Заморозка сейчас не нужна",
                "У вас нет активных занятий, которые можно отправить на заморозку.",
                next_step="Если ситуация изменится, вы сможете вернуться к этой кнопке позже.",
                icon="ℹ️",
            ),
            reply_markup=back_to_menu_keyboard,
        )
        await state.clear()
        await callback_query.answer()
        return

    await state.set_state(FreezeConfirm.waiting_for_confirm)
    await state.update_data(
        freeze_reason=reason,
        freeze_active_count=active_count,
        freeze_student_id=learning_user_id,
    )

    await callback_query.message.edit_text(
        build_freeze_confirm_text(label, active_count),
        reply_markup=make_freeze_confirm_keyboard(reason),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('freeze_confirm:'),
    StateFilter(FreezeConfirm.waiting_for_confirm),
)
async def process_freeze_confirm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if await _block_preview_action(callback_query, db, clear_state=state):
        return

    reason = callback_query.data.split(':', 1)[1]
    state_data = await state.get_data()
    freeze_student_id = state_data.get("freeze_student_id")
    if freeze_student_id is None:
        freeze_student_id = await _get_learning_student_id(db, callback_query.from_user.id)
    user_id = int(freeze_student_id)

    async with db.pool.acquire() as conn:
        active = await conn.fetch(
            "SELECT id FROM lessons WHERE student_id = $1 AND status = 'active'", user_id
        )
        if not active:
            await callback_query.message.edit_text(
                build_action_result_text(
                    "Заморозка сейчас не нужна",
                    "У вас нет активных занятий, которые можно отправить на заморозку.",
                    icon="ℹ️",
                ),
                reply_markup=back_to_menu_keyboard,
            )
            await state.clear()
            await callback_query.answer()
            return

        await conn.execute(
            """
            UPDATE lessons
            SET status = 'freeze_pending',
                freeze_reason = $1,
                freeze_start_date = CURRENT_TIMESTAMP
            WHERE student_id = $2 AND status = 'active'
            """,
            reason, user_id,
        )

    await state.clear()

    label = FREEZE_REASON_LABELS.get(reason, reason)
    admin_id = config.ADMIN_ID
    if admin_id:
        await callback_query.bot.send_message(
            admin_id,
            f"❄️ <b>Новая заявка на заморозку!</b>\n\n"
            f"👤 Ученик: {html.quote(callback_query.from_user.full_name)}\n"
            f"Причина: {label}\n"
            f"Затронуто занятий: {len(active)}",
        )
    add_inbox_event = getattr(db, "add_inbox_event", None)
    if callable(add_inbox_event):
        try:
            await add_inbox_event("freeze_request", {
                "telegram_id": callback_query.from_user.id,
                "full_name": callback_query.from_user.full_name or str(callback_query.from_user.id),
                "context": "freeze",
                "reason": label,
                "lessons_affected": len(active),
                "message_preview": f"Заморозка: {label}",
            })
        except Exception:
            logger.warning("Не удалось записать freeze_request в admin_inbox", exc_info=True)

    await callback_query.message.edit_text(
        build_freeze_success_text(label, state_data.get("freeze_active_count", len(active))),
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()
