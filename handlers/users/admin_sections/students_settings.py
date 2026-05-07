"""Обработчики переключения настроек ученика (формат, обращение, тип, стадия)."""
from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import is_admin, q
from handlers.users.admin_sections._students_helpers import (
    _render_admin_lesson_formats,
    _render_admin_speech_styles,
    _render_admin_student_card,
    _render_admin_student_settings,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    make_admin_student_stage_keyboard,
)
from utils.db_api.postgresql import Database
from utils.ui_text import lesson_format_label
from utils.speech import normalize_speech_style, speech_style_label

router = Router()


@router.callback_query(lambda c: c.data.startswith("admin:student_format:"))
async def admin_student_format_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, target_format = callback_query.data.split(":")
    if target_format not in {"online", "offline"}:
        await callback_query.answer("Неизвестный формат.", show_alert=True)
        return
    student_id = int(student_id_str)
    page = int(page_str)
    await db.set_lesson_format(student_id, target_format)
    await _render_admin_student_settings(callback_query.message, db, student_id, page)
    await callback_query.answer(f"Формат переключён: {lesson_format_label(target_format)}")


@router.callback_query(lambda c: c.data.startswith("admin:student_speech_style:"))
async def admin_student_speech_style_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, target_style = callback_query.data.split(":")
    target_style = normalize_speech_style(target_style)
    student_id = int(student_id_str)
    page = int(page_str)
    await db.set_speech_style(student_id, target_style)
    await _render_admin_student_settings(callback_query.message, db, student_id, page)
    await callback_query.answer(f"Обращение переключено: {speech_style_label(target_style)}")


@router.callback_query(lambda c: c.data.startswith("admin:student_homework_exempt:"))
async def admin_student_homework_exempt_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if len(parts) != 5 or parts[4] not in {"0", "1"}:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    student_id = int(parts[2])
    page = int(parts[3])
    target_value = parts[4] == "1"
    await db.set_homework_exempt(student_id, target_value)
    await _render_admin_student_settings(callback_query.message, db, student_id, page)
    answer = "Не задаю ДЗ этому ученику." if target_value else "Снова задаю ДЗ этому ученику."
    await callback_query.answer(answer)


@router.callback_query(lambda c: c.data.startswith("admin:student_homework_exempt_card:"))
async def admin_student_homework_exempt_card_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if len(parts) != 5 or parts[4] not in {"0", "1"}:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    student_id = int(parts[2])
    page = int(parts[3])
    target_value = parts[4] == "1"
    await db.set_homework_exempt(student_id, target_value)
    await _render_admin_student_card(callback_query.message, db, student_id, page)
    answer = "Не задаю ДЗ этому ученику." if target_value else "Снова задаю ДЗ этому ученику."
    await callback_query.answer(answer)


@router.callback_query(lambda c: c.data.startswith("admin:student_type_toggle:"))
async def admin_student_type_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    page = int(parts[3])
    new_type = await db.toggle_student_type(student_id)
    label = "Школьник" if new_type == "schoolchild" else "Взрослый"
    await _render_admin_student_settings(callback_query.message, db, student_id, page)
    await callback_query.answer(f"Тип переключён: {label}")


@router.callback_query(lambda c: c.data.startswith("admin:student_stage:"))
async def admin_student_stage(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    page = int(parts[3])
    student = await db.get_user(student_id)
    if not student:
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return
    from utils.ui_text import STUDENT_STAGES, compute_student_stage, student_stage_badge

    first_dt = student.get("cached_first_lesson_date") or student.get("first_lesson_date")
    override = student.get("student_stage_override")
    current = compute_student_stage(first_dt, override=override)
    is_overridden = bool(override and override in STUDENT_STAGES)
    badge = student_stage_badge(first_dt, override=override)
    suffix = " (вручную)" if is_overridden else " (авто)"
    auto_badge = student_stage_badge(first_dt)
    text = (
        f"📊 <b>Стадия ученика</b>\n\n"
        f"👤 {q(student['full_name'])}\n"
        f"Текущая: <b>{badge}{suffix}</b>\n"
        f"Авто-определение: <b>{auto_badge}</b>\n\n"
        f"Выберите стадию или оставьте авто-определение."
    )
    await callback_query.message.edit_text(
        text,
        reply_markup=make_admin_student_stage_keyboard(student_id, page, current, is_overridden),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_stage_set:"))
async def admin_student_stage_set(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    page = int(parts[3])
    target = parts[4]
    from utils.ui_text import STUDENT_STAGES, student_stage_label

    if target == "auto":
        await db.set_student_stage_override(student_id, None)
        await callback_query.answer("Стадия вернулась к авто-определению.")
    elif target in STUDENT_STAGES:
        await db.set_student_stage_override(student_id, target)
        await callback_query.answer(f"Стадия: {student_stage_label(target)}")
    else:
        await callback_query.answer("Неизвестная стадия.", show_alert=True)
        return
    await _render_admin_student_card(callback_query.message, db, student_id, page)


@router.callback_query(lambda c: c.data.startswith("admin:lesson_format_toggle:"))
async def admin_lesson_format_toggle_list(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, target_format = callback_query.data.split(":")
    if target_format not in {"online", "offline"}:
        await callback_query.answer("Неизвестный формат.", show_alert=True)
        return
    student_id = int(student_id_str)
    await db.set_lesson_format(student_id, target_format)
    await _render_admin_lesson_formats(callback_query.message, db)
    await callback_query.answer(f"Переключено: {lesson_format_label(target_format)}")


@router.callback_query(lambda c: c.data.startswith("admin:speech_style_toggle:"))
async def admin_speech_style_toggle_list(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, target_style = callback_query.data.split(":")
    target_style = normalize_speech_style(target_style)
    student_id = int(student_id_str)
    await db.set_speech_style(student_id, target_style)
    await _render_admin_speech_styles(callback_query.message, db)
    await callback_query.answer(f"Переключено: {speech_style_label(target_style)}")
