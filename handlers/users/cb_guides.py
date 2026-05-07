"""User-guide download callbacks (DOCX per role)."""
from aiogram import Router, types

from data import config
from handlers.users._cb_helpers import _edit_text_for_actor, _resolve_actor_context
from keyboards.inline import make_student_guide_picker_keyboard
from utils.db_api.postgresql import Database
from utils.user_guides import is_valid_guide_kind, send_user_guide


router = Router()


GUIDE_ALLOWED_BY_ROLE = {
    "student": {"student_adult", "student_school"},
    "parent":  {"parent"},
    "admin":   {"student_adult", "student_school", "parent", "admin"},
}


@router.callback_query(lambda c: c.data == "guide:menu:student")
async def process_guide_menu_student(callback_query: types.CallbackQuery, db: Database):
    _, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    is_admin_user = callback_query.from_user.id == config.ADMIN_ID
    if not is_admin_user and (not user or user.get("role") != "student"):
        await callback_query.answer("Этот выбор доступен ученикам.", show_alert=True)
        return
    await _edit_text_for_actor(
        callback_query.message,
        "📥 <b>Инструкция к боту</b>\n\n"
        "Выбери версию: для взрослого ученика или для школьника. "
        "Файл придёт прямо в чат.",
        make_student_guide_picker_keyboard(),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("guide:send:"))
async def process_guide_send(callback_query: types.CallbackQuery, db: Database):
    parts = callback_query.data.split(":")
    if len(parts) != 3:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    kind = parts[2]
    if not is_valid_guide_kind(kind):
        await callback_query.answer("Этой инструкции нет.", show_alert=True)
        return

    is_admin_user = callback_query.from_user.id == config.ADMIN_ID
    user = await db.get_user(callback_query.from_user.id)
    role = (user or {}).get("role") if user else None
    effective_role = "admin" if is_admin_user else role
    if not effective_role:
        await callback_query.answer("Сначала зарегистрируйся в боте.", show_alert=True)
        return
    allowed = GUIDE_ALLOWED_BY_ROLE.get(effective_role, set())
    if kind not in allowed:
        await callback_query.answer("Этот файл доступен другой роли.", show_alert=True)
        return

    sent = await send_user_guide(callback_query.bot, callback_query.from_user.id, kind)
    if not sent:
        await callback_query.answer(
            "Файл инструкции не найден на сервере. Сообщите администратору.",
            show_alert=True,
        )
        return
    await callback_query.answer("Файл отправлен.")
