from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from data import config
from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_inbox_keyboard,
    make_admin_inbox_item_keyboard,
)
from states.registration import AdminAddPayment
from utils.db_api.postgresql import Database
from utils.ui_text import build_admin_inbox_item_text, build_admin_inbox_text

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


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


async def _get_inbox_event(db: Database, event_id: int):
    get_event = getattr(db, "get_inbox_event", None)
    if callable(get_event):
        return await get_event(event_id)
    rows = await db.execute(
        "SELECT id, kind, payload, created_at, read_at, handled_at, handled_by FROM admin_inbox WHERE id = $1",
        event_id,
        fetch=True,
    )
    return rows[0] if rows else None


async def render_admin_inbox_item(message, db: Database, event_id: int) -> bool:
    event = await _get_inbox_event(db, event_id)
    if not event:
        return False

    payload = _payload_dict(event.get("payload"))
    text = build_admin_inbox_item_text(event)
    keyboard = make_admin_inbox_item_keyboard(
        event_id,
        event.get("kind") or "",
        context=payload.get("context"),
        student_id=payload.get("student_id"),
    )
    await message.edit_text(text, reply_markup=keyboard)
    return True


@router.callback_query(lambda c: c.data == "admin:inbox")
async def admin_inbox_screen(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Недоступно.", show_alert=True)
        return

    events = list(await db.get_unread_inbox(limit=20) or [])
    text = build_admin_inbox_text(events)
    keyboard = make_admin_inbox_keyboard(events)
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:inbox:noop")
async def admin_inbox_noop(callback_query: types.CallbackQuery):
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:inbox:item:") and not c.data.endswith(":close"))
async def admin_inbox_item_screen(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Недоступно.", show_alert=True)
        return

    parts = callback_query.data.split(":")
    try:
        event_id = int(parts[3])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка: неверный формат.", show_alert=True)
        return

    if not await render_admin_inbox_item(callback_query.message, db, event_id):
        await callback_query.answer("Событие не найдено.", show_alert=True)
        return
    await callback_query.answer()


@router.callback_query(lambda c: c.data.endswith(":close") and c.data.startswith("admin:inbox:item:"))
async def admin_inbox_item_close(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Недоступно.", show_alert=True)
        return

    parts = callback_query.data.split(":")
    try:
        event_id = int(parts[3])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка: неверный формат.", show_alert=True)
        return

    try:
        await db.mark_inbox_read(event_id, callback_query.from_user.id)
    except Exception:
        logger.warning("Не удалось закрыть событие inbox %s", event_id, exc_info=True)

    events = list(await db.get_unread_inbox(limit=20) or [])
    text = build_admin_inbox_text(events)
    keyboard = make_admin_inbox_keyboard(events)
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer("Закрыто.")


@router.callback_query(lambda c: c.data == "admin:inbox:mark_all_read")
async def admin_inbox_mark_all_read(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Недоступно.", show_alert=True)
        return

    count = await db.mark_all_inbox_read(callback_query.from_user.id)

    events = list(await db.get_unread_inbox(limit=20) or [])
    text = build_admin_inbox_text(events)
    keyboard = make_admin_inbox_keyboard(events)
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer(f"Отмечено прочитанным: {count}.")


@router.callback_query(lambda c: c.data.startswith("admin:inbox:reply:"))
async def admin_inbox_reply(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Недоступно.", show_alert=True)
        return

    parts = callback_query.data.split(":")
    try:
        event_id = int(parts[3])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка: неверный формат.", show_alert=True)
        return

    rows = await db.execute(
        "SELECT id, kind, payload, created_at FROM admin_inbox WHERE id = $1",
        event_id,
        fetch=True,
    )
    if not rows:
        await callback_query.answer("Событие не найдено.", show_alert=True)
        return

    import json
    event = rows[0]
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    student_id = payload.get("telegram_id")
    if not student_id:
        await callback_query.answer(
            "Нет telegram_id получателя. Используйте раздел Ученики для ответа.",
            show_alert=True,
        )
        return

    from keyboards.inline import make_write_to_student_keyboard
    name = payload.get("full_name") or str(student_id)
    await callback_query.message.edit_text(
        f"✉️ Ответ на inbox-событие #{event_id}\n\n"
        f"👤 Получатель: {name}\n\n"
        "Используйте кнопку «✉️ Написать ученику» ниже, чтобы перейти к FSM-ответу.",
        reply_markup=make_write_to_student_keyboard(int(student_id)),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:inbox:add_payment:"))
async def admin_inbox_add_payment(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer("Недоступно.", show_alert=True)
        return

    parts = callback_query.data.split(":")
    try:
        event_id = int(parts[3])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка: неверный формат.", show_alert=True)
        return

    event = await _get_inbox_event(db, event_id)
    if not event:
        await callback_query.answer("Событие не найдено.", show_alert=True)
        return

    payload = _payload_dict(event.get("payload"))
    student_id = payload.get("student_id")
    payer_id = payload.get("telegram_id")
    if not student_id:
        await callback_query.answer("Нет ученика для оплаты.", show_alert=True)
        return

    await state.clear()
    await state.set_state(AdminAddPayment.waiting_for_payment_amount)
    await state.update_data(
        student_id=int(student_id),
        admin_payment_payer_id=int(payer_id) if payer_id else int(student_id),
        admin_inbox_event_id=event_id,
        admin_return_view=f"admin:inbox:item:{event_id}",
        admin_origin_chat_id=callback_query.message.chat.id,
        admin_origin_message_id=callback_query.message.message_id,
    )
    child_label = payload.get("child_label") or str(student_id)
    payer_name = payload.get("full_name") or str(payer_id or "")
    await callback_query.message.edit_text(
        "\n".join([
            "💳 <b>Провести оплату из входящего</b>",
            "",
            f"Ученик: <b>{child_label}</b>",
            f"Плательщик: <b>{payer_name}</b>",
            "",
            "Введите сумму оплаты.",
        ]),
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()
