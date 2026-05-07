"""Обработчики карточки ученика: просмотр, общение, длительность, тариф, итоги урока."""
from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import (
    extract_broadcast_payload,
    get_message_origin,
    is_admin,
    message_to_html,
    q,
    restore_admin_view,
)
from handlers.users.admin_sections._students_helpers import (
    _followup_prompt_context,
    _render_admin_student_actions,
    _render_admin_student_card,
    _render_admin_student_danger,
    _render_admin_student_settings,
    _write_to_student_result_keyboard,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_back_button_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import (
    AdminEditPreferredName,
    AdminLessonFollowup,
    AdminWriteToStudent,
)
from utils.db_api.postgresql import Database
from utils.ui_text import (
    build_action_result_text,
    build_tariff_picker_text,
    format_datetime,
)

router = Router()


async def _show_student_card(callback_query: types.CallbackQuery, db: Database, student_id: int, page: int = 0):
    """Вспомогательная функция для открытия карточки ученика из внешнего кода (pulse.py)."""
    await _render_admin_student_card(callback_query.message, db, student_id, page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_card:"))
async def admin_student_card(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_card(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_actions:"))
async def admin_student_actions(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_actions(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_settings:"))
async def admin_student_settings(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_settings(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_danger:"))
async def admin_student_danger(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_danger(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:write_to_student:"))
async def admin_write_to_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    source = parts[4] if len(parts) > 4 else "card"
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        student_name=student["full_name"],
        admin_return_view=(
            f"admin:student_{source}:{student_id}:{page}"
            if page is not None and source in {"actions", "settings", "danger"}
            else (f"admin:student_card:{student_id}:{page}" if page is not None else None)
        ),
        admin_origin_chat_id=origin_chat_id if page is not None else None,
        admin_origin_message_id=origin_message_id if page is not None else None,
        admin_student_card_page=page,
        admin_student_card_source=source,
    )
    await state.set_state(AdminWriteToStudent.waiting_for_message)
    await callback_query.message.edit_text(
        f"✉️ Отправьте сообщение для ученика <b>{q(student['full_name'])}</b>.\n\n"
        "Можно отправить текст, GIF, стикер, фото, документ, голосовое или видео.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminWriteToStudent.waiting_for_message))
async def admin_write_to_student_send(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Отправка доступна только администратору.", reply_markup=back_to_admin_keyboard)
        return

    payload = extract_broadcast_payload(message)
    if not payload:
        await message.answer(
            "⚠️ Отправьте текст, GIF, стикер или другое сообщение, которое нужно переслать ученику.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data["student_id"]
    page = data.get("admin_student_card_page")
    source = data.get("admin_student_card_source", "card")
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await state.clear()
        await message.answer("⚠️ Ученик не найден.", reply_markup=back_to_admin_keyboard)
        return

    try:
        if payload["mode"] == "copy":
            await message.bot.copy_message(
                chat_id=student_id,
                from_chat_id=payload["source_chat_id"],
                message_id=payload["source_message_id"],
                reply_markup=make_teacher_reply_keyboard("teacher_message"),
            )
        else:
            await message.bot.send_message(
                student_id,
                payload["text"],
                reply_markup=make_teacher_reply_keyboard("teacher_message"),
            )
    except Exception:
        await message.answer(
            "⚠️ Не удалось отправить сообщение ученику. Попробуйте ещё раз.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await state.clear()
    await restore_admin_view(
        message.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )
    await message.answer(
        build_action_result_text(
            "Сообщение отправлено",
            f"Ученик: <b>{q(student['full_name'])}</b>.",
            next_step="При необходимости можно сразу отправить ещё одно сообщение из карточки ученика.",
        ),
        reply_markup=_write_to_student_result_keyboard(student_id, page, source),
    )


@router.callback_query(lambda c: c.data.startswith("admin:student_duration:"))
async def admin_student_duration_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, student_id_str, page_str = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        student_name=student["full_name"],
        admin_return_view=f"admin:student_settings:{student_id}:{page}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
        admin_student_card_page=page,
        admin_student_card_source="settings",
    )
    await state.set_state(AdminLessonFollowup.waiting_for_lesson_duration)
    await callback_query.message.edit_text(
        f"⏱ Введите длительность урока для <b>{q(student['full_name'])}</b> в минутах.\n\n"
        "Разрешён диапазон: <code>30..180</code>.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminLessonFollowup.waiting_for_lesson_duration))
async def admin_student_duration_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Изменение доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    try:
        minutes = int((message.text or "").strip())
    except ValueError:
        minutes = 0

    if not 30 <= minutes <= 180:
        await message.answer(
            "⚠️ Нужна целая длительность в диапазоне <code>30..180</code> минут.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data["student_id"]
    student_name = q(data.get("student_name") or student_id)
    page = data.get("admin_student_card_page")
    source = data.get("admin_student_card_source", "card")
    await db.set_lesson_duration(student_id, minutes)

    await state.clear()
    await restore_admin_view(
        message.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )
    await message.answer(
        build_action_result_text(
            "Длительность урока обновлена",
            f"👤 Ученик: <b>{student_name}</b>\n⏱ Новая длительность: <b>{minutes} мин</b>",
            next_step="Новая длительность уже будет учитываться в post-lesson сообщениях.",
        ),
        reply_markup=_write_to_student_result_keyboard(student_id, page, source),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:student_preferred_name:"), StateFilter("*"))
async def admin_student_preferred_name_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    try:
        student_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    student = await db.get_user(student_id)
    if not student:
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return
    name = student.get("full_name", str(student_id))
    current = student.get("preferred_name") or "—"
    await state.clear()
    await state.update_data(preferred_name_student_id=student_id, preferred_name_page=page)
    await state.set_state(AdminEditPreferredName.waiting_for_text)
    await callback_query.message.edit_text(
        "\n".join([
            f"✏️ <b>Имя для обращения: {q(name)}</b>",
            "",
            f"Текущее: <b>{q(current)}</b>",
            "",
            "Пришлите имя в именительном падеже («Иван», «Полина»). Бот будет использовать его в личных сообщениях ученику.",
        ]),
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminEditPreferredName.waiting_for_text))
async def admin_student_preferred_name_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    student_id = data.get("preferred_name_student_id")
    page = int(data.get("preferred_name_page") or 0)
    raw = (message.text or "").strip()
    new_value = raw if raw and raw != "—" else None
    if student_id is None:
        await state.clear()
        return
    await db.update_student_preferred_name(int(student_id), new_value)
    await state.clear()
    student = await db.get_user(int(student_id))
    student_name = q(student.get("full_name", str(student_id))) if student else str(student_id)
    shown = q(new_value) if new_value else "—"
    await message.answer(
        build_action_result_text(
            "Имя для обращения обновлено",
            f"👤 Ученик: <b>{student_name}</b>\n✏️ Новое имя: <b>{shown}</b>",
            next_step="Бот будет использовать это имя в межурочных касаниях.",
        ),
        reply_markup=_write_to_student_result_keyboard(int(student_id), page, "settings"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:student_tariff:"), StateFilter("*"))
async def admin_student_tariff_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    # Format: admin:student_tariff:{student_id}:{page}
    parts = callback_query.data.split(":")
    try:
        student_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    student = await db.get_user(student_id)
    name = student.get("full_name", str(student_id)) if student else str(student_id)
    rates = list(await db.get_pricing_rates() or [])
    current_rate_id = student.get("pricing_rate_id") if student else None

    from keyboards.inline import make_tariff_picker_keyboard
    await callback_query.message.edit_text(
        build_tariff_picker_text(q(name), rates, current_rate_id),
        reply_markup=make_tariff_picker_keyboard(student_id, page, rates, current_rate_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:assign_tariff:"))
async def admin_assign_tariff(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    # Format: admin:assign_tariff:{student_id}:{rate_id}:{page}
    parts = callback_query.data.split(":")
    try:
        student_id = int(parts[2])
        rate_id = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 0
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    await db.assign_pricing_rate(student_id, rate_id if rate_id > 0 else None)
    await callback_query.answer("Тариф назначен." if rate_id > 0 else "Тариф снят.")
    await _render_admin_student_card(callback_query.message, db, student_id, page)


@router.callback_query(lambda c: c.data.startswith("lesson_followup:comment:"))
async def lesson_followup_comment_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    lesson_id = int(callback_query.data.split(":")[2])
    lesson = await db.get_lesson_context(lesson_id)
    if not lesson:
        await callback_query.answer("Урок не найден.", show_alert=True)
        return

    student_name, lesson_label = _followup_prompt_context(lesson)
    await state.clear()
    await state.update_data(
        followup_lesson_id=lesson_id,
        followup_student_id=lesson["student_id"],
        followup_student_name=student_name,
        followup_lesson_label=lesson_label,
    )
    await state.set_state(AdminLessonFollowup.waiting_for_lesson_comment)
    await callback_query.message.edit_text(
        f"💬 Напишите приватный комментарий по уроку с <b>{student_name}</b>.\n"
        f"📅 Урок: <b>{lesson_label}</b>",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminLessonFollowup.waiting_for_lesson_comment))
async def lesson_followup_comment_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Сохранение доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    comment_html = message_to_html(message)
    if not comment_html:
        await message.answer(
            "⚠️ Пришлите текстовый комментарий по уроку.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    await db.save_teacher_comment(data["followup_lesson_id"], comment_html)
    await state.clear()
    await message.answer(
        build_action_result_text(
            "Комментарий сохранён",
            f"👤 Ученик: <b>{data['followup_student_name']}</b>\n📅 Урок: <b>{data['followup_lesson_label']}</b>",
            next_step="Комментарий привязан только к этому уроку и не попадёт в reminder перед следующим занятием.",
        ),
        reply_markup=back_to_admin_keyboard,
    )


@router.callback_query(lambda c: c.data.startswith("lesson_followup:bookmark:"))
async def lesson_followup_bookmark_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, lesson_id_str, student_id_str = callback_query.data.split(":")
    lesson_id = int(lesson_id_str)
    student_id = int(student_id_str)
    lesson = await db.get_lesson_context(lesson_id)
    if not lesson or lesson["student_id"] != student_id:
        await callback_query.answer("Урок или ученик не найдены.", show_alert=True)
        return

    student_name, lesson_label = _followup_prompt_context(lesson)
    await state.clear()
    await state.update_data(
        followup_lesson_id=lesson_id,
        followup_student_id=student_id,
        followup_student_name=student_name,
        followup_lesson_label=lesson_label,
    )
    await state.set_state(AdminLessonFollowup.waiting_for_lesson_bookmark)
    await callback_query.message.edit_text(
        f"📖 Напишите закладку по учебнику или книге для <b>{student_name}</b>.\n"
        f"📅 Последний урок: <b>{lesson_label}</b>\n\n"
        "Этот текст придёт вам перед следующим занятием с этим учеником.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminLessonFollowup.waiting_for_lesson_bookmark))
async def lesson_followup_bookmark_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Сохранение доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    bookmark_html = message_to_html(message)
    if not bookmark_html:
        await message.answer(
            "⚠️ Пришлите текстовую закладку по учебнику или книге.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    await db.save_student_bookmark(
        data["followup_student_id"],
        data["followup_lesson_id"],
        bookmark_html,
        "saved",
    )
    await state.clear()
    await message.answer(
        build_action_result_text(
            "Закладка сохранена",
            f"👤 Ученик: <b>{data['followup_student_name']}</b>\n📅 Последний урок: <b>{data['followup_lesson_label']}</b>",
            next_step="Перед следующим уроком бот пришлёт вам эту закладку автоматически.",
        ),
        reply_markup=back_to_admin_keyboard,
    )


@router.callback_query(lambda c: c.data.startswith("lesson_followup:no_material:"))
async def lesson_followup_no_material(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, lesson_id_str, student_id_str = callback_query.data.split(":")
    lesson_id = int(lesson_id_str)
    student_id = int(student_id_str)
    lesson = await db.get_lesson_context(lesson_id)
    if not lesson or lesson["student_id"] != student_id:
        await callback_query.answer("Урок или ученик не найдены.", show_alert=True)
        return

    await db.save_student_bookmark(student_id, lesson_id, None, "no_material")
    await callback_query.message.edit_text(
        build_action_result_text(
            "Закладка очищена",
            f"👤 Ученик: <b>{q(lesson['full_name'])}</b>\n📅 Последний урок: <b>{format_datetime(lesson.get('lesson_date'))}</b>",
            next_step="Перед следующим уроком бот всё равно напомнит, что по учебнику или книге в прошлый раз не работали.",
        ),
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer("Отмечено: без учебника/книги")
