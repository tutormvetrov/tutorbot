"""Reply/messaging system callbacks."""
import logging

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from handlers.users._cb_helpers import (
    _block_preview_action,
    _open_reply_prompt,
    _resolve_actor_context,
    REPLY_CONTEXT_LABELS,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    back_to_menu_keyboard,
    make_write_to_student_keyboard,
)
from states.registration import StudentReply
from utils.db_api.postgresql import Database
from utils.homework_text import homework_preview_text
from utils.preview_mode import PREVIEW_BLOCKED_ALERT, get_preview_context
from utils.ui_text import build_action_result_text

logger = logging.getLogger(__name__)

router = Router()


async def _build_reply_context_label(
    db: Database,
    context_key: str,
    entity_id: int | None,
    *,
    parent_id: int | None = None,
    child_link_id: int | None = None,
) -> str:
    if context_key == "homework" and entity_id:
        hw = await db.get_homework_by_id(entity_id)
        if hw:
            preview = html.quote(
                homework_preview_text(
                    hw.get("title"),
                    hw.get("description"),
                    attachment_name=hw.get("attachment_name"),
                    attachment_mime_type=hw.get("attachment_mime_type"),
                )
            )
            return f"по домашнему заданию «{preview}»"
    if context_key == "payment" and parent_id and child_link_id:
        child = await db.get_parent_child_link(parent_id, child_link_id)
        if child:
            child_name = (child.get("child_label") or child.get("student_info") or "").strip()
            if child_name:
                return f"по оплате за {html.quote(child_name)}"
    return REPLY_CONTEXT_LABELS.get(context_key, "без уточнения темы")


@router.callback_query(lambda c: c.data.startswith('reply:'), StateFilter('*'))
async def start_student_reply(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if await _block_preview_action(callback_query, db, clear_state=state):
        return

    _, user, _ = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user["role"] not in {"student", "parent"}:
        await callback_query.answer("Ответ доступен только зарегистрированным пользователям.", show_alert=True)
        return

    if not config.ADMIN_ID:
        await callback_query.answer("ADMIN_ID не настроен.", show_alert=True)
        return

    parts = callback_query.data.split(':')
    context_key = parts[1] if len(parts) > 1 else "general"
    entity_id: int | None = None
    child_link_id: int | None = None
    if len(parts) > 2:
        if parts[2] == "child" and len(parts) > 3 and parts[3].isdigit():
            child_link_id = int(parts[3])
        elif parts[2].isdigit():
            entity_id = int(parts[2])
    if user["role"] == "parent" and context_key not in {"general", "payment"}:
        await callback_query.answer("Этот тип ответа сейчас доступен только ученикам.", show_alert=True)
        return
    context_label = await _build_reply_context_label(
        db,
        context_key,
        entity_id,
        parent_id=callback_query.from_user.id if user["role"] == "parent" else None,
        child_link_id=child_link_id,
    )
    child_payload: dict = {}
    if user["role"] == "parent" and context_key == "payment" and child_link_id:
        child = await db.get_parent_child_link(callback_query.from_user.id, child_link_id)
        if child:
            child_payload = {
                "reply_student_id": child.get("student_id"),
                "reply_child_label": child.get("child_label") or child.get("student_info"),
            }

    await state.clear()
    await state.set_state(StudentReply.waiting_for_message)
    await state.update_data(
        reply_context_key=context_key,
        reply_entity_id=entity_id,
        reply_child_link_id=child_link_id,
        reply_context_label=context_label,
        **child_payload,
    )

    await _open_reply_prompt(
        callback_query.message,
        "✉️ Напишите сообщение для преподавателя.\n\n"
        f"Контекст: <b>{context_label}</b>\n\n"
        "Можно отправить текст, фото, документ, голосовое, GIF или стикер.",
    )
    await callback_query.answer()


@router.message(StateFilter(StudentReply.waiting_for_message))
async def process_student_reply_message(message: types.Message, state: FSMContext, db: Database):
    if await get_preview_context(db, message.from_user.id):
        await state.clear()
        await message.answer(
            PREVIEW_BLOCKED_ALERT,
            reply_markup=back_to_admin_keyboard,
        )
        return

    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in {"student", "parent"}:
        await state.clear()
        await message.answer(
            "⚠️ Ответ сейчас доступен только зарегистрированным пользователям.",
            reply_markup=back_to_menu_keyboard,
        )
        return

    if not config.ADMIN_ID:
        await state.clear()
        await message.answer(
            "⚠️ ADMIN_ID не настроен. Сообщение не отправлено.",
            reply_markup=back_to_menu_keyboard,
        )
        return

    data = await state.get_data()
    context_label = data.get("reply_context_label", "без уточнения темы")
    student_name = html.quote(user["full_name"] or message.from_user.full_name or str(message.from_user.id))
    username = f"@{message.from_user.username}" if message.from_user.username else "—"
    sender_title = "родителя" if user["role"] == "parent" else "ученика"

    await message.bot.send_message(
        config.ADMIN_ID,
        f"✉️ <b>Сообщение от {sender_title}</b>\n\n"
        f"👤 {student_name}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"🔗 Username: {html.quote(username)}\n"
        f"🧭 Контекст: <b>{context_label}</b>",
        reply_markup=make_write_to_student_keyboard(message.from_user.id),
    )
    try:
        await message.copy_to(config.ADMIN_ID)
    except Exception:
        fallback_text = message.text or message.caption or "[Сообщение без текста]"
        await message.bot.send_message(
            config.ADMIN_ID,
            f"⚠️ Не удалось переслать оригинал автоматически.\n\n{html.quote(fallback_text)}",
        )

    add_inbox_event = getattr(db, "add_inbox_event", None)
    if callable(add_inbox_event):
        try:
            await add_inbox_event("reply", {
                "telegram_id": message.from_user.id,
                "full_name": user["full_name"] or str(message.from_user.id),
                "context": data.get("reply_context_key", "general"),
                "message_preview": (message.text or message.caption or "")[:200],
                "role": user["role"],
                "child_link_id": data.get("reply_child_link_id"),
                "student_id": data.get("reply_student_id"),
                "child_label": data.get("reply_child_label"),
            })
        except Exception:
            logger.warning("Не удалось записать reply в admin_inbox", exc_info=True)

    await state.clear()
    await message.answer(
        build_action_result_text(
            "Сообщение отправлено",
            "Преподаватель получит его в ближайшее время.",
            next_step="Если нужно, можно вернуться в меню и продолжить работу с ботом.",
        ),
        reply_markup=back_to_menu_keyboard,
    )
