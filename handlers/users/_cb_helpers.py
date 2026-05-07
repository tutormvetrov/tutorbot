"""Shared constants and helper functions used by multiple callback modules."""
import logging

from aiogram import types
from aiogram.fsm.context import FSMContext

from keyboards.inline import cancel_fsm_keyboard
from utils.db_api.postgresql import Database
from utils.preview_mode import (
    PREVIEW_BLOCKED_ALERT,
    apply_preview_to_payload,
    get_preview_context,
    get_preview_parent_child_homework,
    get_preview_parent_child_link,
    get_preview_parent_child_payments,
    get_preview_parent_child_schedule,
    is_synthetic_parent_preview,
)
from utils.ui_text import build_self_delete_warning_text

logger = logging.getLogger(__name__)

REPLY_CONTEXT_LABELS = {
    "homework": "по домашнему заданию",
    "payment": "по оплате",
    "lesson": "по ближайшему занятию",
    "broadcast": "по сообщению от преподавателя",
    "freeze": "по заморозке",
    "teacher_message": "по сообщению от преподавателя",
    "review": "по просьбе оставить отзыв",
    "general": "без уточнения темы",
}

LESSON_PRESENCE_LABELS = {
    "on_time": "✅ Буду вовремя",
    "late": "⏱ Немного задержусь",
}


def _build_self_delete_warning(user, snapshot: dict) -> str:
    return build_self_delete_warning_text(user, snapshot)


async def _resolve_actor_context(db: Database, actor_id: int):
    preview = await get_preview_context(db, actor_id)
    if preview:
        return preview["target_id"], preview["user"], preview
    get_user = getattr(db, "get_user", None)
    user = await get_user(actor_id) if callable(get_user) else None
    return actor_id, user, None


async def _get_learning_student_id(db: Database, student_id: int) -> int:
    get_pair = getattr(db, "get_student_pair_for_student", None)
    if callable(get_pair):
        pair = await get_pair(student_id)
        if pair:
            return int(pair["primary_student_id"])
    return student_id


async def _edit_text_for_actor(message: types.Message, text: str, reply_markup, preview: dict | None):
    text, reply_markup = apply_preview_to_payload(text, reply_markup, preview)
    await message.edit_text(text, reply_markup=reply_markup)


def _message_needs_reply_prompt_fallback(message: types.Message) -> bool:
    return any(
        getattr(message, field, None)
        for field in ("sticker", "photo", "video", "document", "voice", "animation")
    )


async def _open_reply_prompt(message: types.Message, text: str):
    if _message_needs_reply_prompt_fallback(message):
        await message.answer(text, reply_markup=cancel_fsm_keyboard)
        return

    try:
        await message.edit_text(text, reply_markup=cancel_fsm_keyboard)
    except Exception:
        logger.warning("Failed to open reply prompt via edit_text, using answer() instead", exc_info=True)
        await message.answer(text, reply_markup=cancel_fsm_keyboard)


async def _block_preview_action(callback_query: types.CallbackQuery, db: Database, *, clear_state: FSMContext | None = None) -> bool:
    preview = await get_preview_context(db, callback_query.from_user.id)
    if not preview:
        return False
    if clear_state is not None:
        await clear_state.clear()
    await callback_query.answer(PREVIEW_BLOCKED_ALERT, show_alert=True)
    return True


async def _get_parent_child_link(
    db: Database,
    parent_id: int,
    link_id: int,
    preview: dict | None = None,
):
    if is_synthetic_parent_preview(preview):
        return await get_preview_parent_child_link(db, preview, link_id)
    return await db.get_parent_child_link(parent_id, link_id)


def _resolve_engagement_mode(user: dict | None) -> str:
    if not user:
        return "active"
    mode = (user.get("engagement_mode") or "").strip()
    return mode if mode in {"active", "trust"} else "active"


async def _get_parent_child_schedule(
    db: Database,
    parent_id: int,
    link_id: int,
    preview: dict | None = None,
):
    if is_synthetic_parent_preview(preview):
        return await get_preview_parent_child_schedule(db, preview, link_id)
    return await db.get_parent_child_schedule(parent_id, link_id)


async def _get_parent_child_homework(
    db: Database,
    parent_id: int,
    link_id: int,
    status: str,
    preview: dict | None = None,
):
    if is_synthetic_parent_preview(preview):
        return await get_preview_parent_child_homework(db, preview, link_id, status=status)
    return await db.get_parent_child_homework(parent_id, link_id, status=status)


async def _get_parent_child_payments(
    db: Database,
    parent_id: int,
    link_id: int,
    limit: int,
    preview: dict | None = None,
):
    if is_synthetic_parent_preview(preview):
        return await get_preview_parent_child_payments(db, preview, link_id, limit=limit)
    return await db.get_parent_child_payments(parent_id, link_id, limit=limit)
