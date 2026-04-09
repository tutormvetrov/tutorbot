import logging
from datetime import datetime

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_context_keyboard,
    make_back_button_keyboard,
    make_homework_delete_confirm_keyboard,
    make_homework_delete_keyboard,
    make_homework_edit_content_keyboard,
    make_homework_edit_deadline_keyboard,
    make_homework_manage_actions_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import AdminAddHomework, AdminEditHomework
from utils.db_api.postgresql import Database
from utils.homework_text import homework_body_html
from utils.ui_text import (
    ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT,
    ADMIN_ADD_HOMEWORK_DEADLINE_INVALID_TEXT,
    ADMIN_ADD_HOMEWORK_DEADLINE_PROMPT_TEXT,
    ADMIN_ADD_HOMEWORK_EMPTY_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    build_admin_homework_description_prompt,
    build_admin_homework_list_text,
)

from handlers.users.admin_sections.common import (
    extract_homework_payload,
    get_message_origin,
    is_admin,
    parse_admin_student_picker_callback_data,
    q,
    render_admin_student_picker,
    restore_admin_view,
)

logger = logging.getLogger(__name__)
router = Router()


def _return_view_from_source(source: str | None) -> str:
    return "admin:cat:education" if source == "education" else "admin:home"


def _reply_markup_for_return_view(return_view: str | None, student_id: int | None = None):
    if return_view:
        if return_view.startswith("admin:student_card:") and student_id is not None:
            parts = return_view.split(":")
            if len(parts) == 4:
                return make_admin_context_keyboard(student_id, int(parts[3]))
        return make_back_button_keyboard("◀️ Вернуться", return_view)
    return make_back_button_keyboard("◀️ Вернуться", return_view or "admin:home")


def _student_return_view(student_id: int, page: int | None, source: str) -> str | None:
    if page is None:
        return None
    if source in {"actions", "settings", "danger"}:
        return f"admin:student_{source}:{student_id}:{page}"
    return f"admin:student_card:{student_id}:{page}"


def _homework_attachment_payload(hw: dict | None) -> dict | None:
    if not hw:
        return None
    file_id = hw.get("attachment_file_id")
    unique_id = hw.get("attachment_file_unique_id")
    file_name = hw.get("attachment_name")
    mime_type = hw.get("attachment_mime_type")
    if not any((file_id, unique_id, file_name, mime_type)):
        return None
    return {
        "file_id": file_id,
        "file_unique_id": unique_id,
        "file_name": file_name,
        "mime_type": mime_type,
    }


def _parse_homework_deadline(value: str | None):
    raw_deadline = (value or "").strip().replace("/", ".").replace("\\", ".")
    if not raw_deadline:
        raise ValueError("empty deadline")
    return datetime.strptime(raw_deadline, "%d.%m.%Y")


def _deadline_label(deadline) -> str:
    return deadline.strftime("%d.%m.%Y") if deadline else "—"


def _build_admin_homework_manage_text(hw: dict, student_name: str) -> str:
    homework_html = homework_body_html(
        hw.get("title"),
        hw.get("description"),
        hw.get("attachment_name"),
        hw.get("attachment_mime_type"),
    ) or "—"
    return (
        "📚 <b>Управление домашним заданием</b>\n\n"
        f"👤 Ученик: <b>{q(student_name)}</b>\n"
        f"📝 Задание:\n{homework_html}\n"
        f"📅 Дедлайн: <b>{_deadline_label(hw.get('deadline'))}</b>\n\n"
        "Ниже можно отредактировать или удалить это ДЗ."
    )


def _build_homework_edit_description_prompt(student_name: str, hw: dict) -> str:
    homework_html = homework_body_html(
        hw.get("title"),
        hw.get("description"),
        hw.get("attachment_name"),
        hw.get("attachment_mime_type"),
    ) or "—"
    return (
        "✏️ <b>Редактирование домашнего задания</b>\n\n"
        f"👤 Ученик: <b>{q(student_name)}</b>\n"
        f"📝 Сейчас:\n{homework_html}\n"
        f"📅 Дедлайн: <b>{_deadline_label(hw.get('deadline'))}</b>\n\n"
        "Отправьте новый текст ДЗ или новый PDF/DOCX.\n"
        "Если пришлёте только текст, текущий файл сохранится.\n"
        "Если пришлёте новый PDF/DOCX, он заменит текущий."
    )


def _build_homework_edit_deadline_prompt(student_name: str, description: str | None, attachment: dict | None, current_deadline: str) -> str:
    homework_html = homework_body_html(
        "",
        description,
        (attachment or {}).get("file_name"),
        (attachment or {}).get("mime_type"),
    ) or "—"
    return (
        "📅 <b>Новый дедлайн</b>\n\n"
        f"👤 Ученик: <b>{q(student_name)}</b>\n"
        f"📝 Обновлённое ДЗ:\n{homework_html}\n"
        f"Текущий дедлайн: <b>{current_deadline}</b>\n\n"
        "Введите новую дату в формате <code>ДД.ММ.ГГГГ</code> "
        "или оставьте текущую кнопкой ниже."
    )


async def _render_admin_homework_list(message: types.Message, db: Database):
    items = await db.get_all_active_homework()
    await message.edit_text(
        build_admin_homework_list_text(items),
        reply_markup=make_homework_delete_keyboard(items) if items else make_back_button_keyboard("◀️ К учебному процессу", "admin:cat:education"),
    )


async def _render_admin_homework_manage(message: types.Message, db: Database, hw_id: int):
    hw = await db.get_homework_by_id(hw_id)
    if not hw:
        await message.edit_text(
            "⚠️ Домашнее задание не найдено.",
            reply_markup=make_back_button_keyboard("◀️ К активным ДЗ", "admin:all_homework"),
        )
        return

    student = await db.get_user(hw["student_id"])
    student_name = q(student["full_name"]) if student else str(hw["student_id"])
    await message.edit_text(
        _build_admin_homework_manage_text(hw, student_name),
        reply_markup=make_homework_manage_actions_keyboard(hw_id),
    )


async def _build_homework_description_prompt(db: Database, student_id: int) -> str:
    try:
        student = await db.get_user(student_id)
        student_name = student["full_name"] if student else str(student_id)
    except Exception:
        student_name = str(student_id)

    try:
        await db.backfill_homework_materials_for_student(student_id)
        recent_mentions = await db.get_recent_homework_material_mentions(student_id)
        top_materials = await db.get_top_homework_materials(student_id)
        latest_mention = await db.get_latest_homework_material_mention(student_id)
        has_homework_history = await db.has_homework_history(student_id)
    except Exception as exc:
        logger.warning("Не удалось собрать статистику по ДЗ для ученика %s: %s", student_id, exc)
        return ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT

    return build_admin_homework_description_prompt(
        student_name=student_name,
        recent_mentions=list(recent_mentions or []),
        top_materials=list(top_materials or []),
        latest_mention=latest_mention,
        has_homework_history=bool(has_homework_history),
    )


async def _prompt_for_homework_description(message: types.Message, state: FSMContext, db: Database, student_id: int):
    prompt_text = await _build_homework_description_prompt(db, student_id)
    await state.set_state(AdminAddHomework.waiting_for_description)
    await message.edit_text(
        prompt_text,
        reply_markup=cancel_fsm_keyboard,
    )


async def _prompt_for_homework_edit_deadline(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(AdminEditHomework.waiting_for_deadline)
    await message.edit_text(
        _build_homework_edit_deadline_prompt(
            data.get("student_name") or str(data.get("student_id") or "—"),
            data.get("description"),
            data.get("attachment"),
            data.get("original_deadline") or "—",
        ),
        reply_markup=make_homework_edit_deadline_keyboard(data.get("original_deadline") or "—"),
    )


async def _finish_homework_edit(message: types.Message, state: FSMContext, db: Database, deadline):
    data = await state.get_data()
    attachment = data.get("attachment")
    description = data.get("description")
    title = data.get("title", "")
    original_attachment = data.get("original_attachment")
    original_description = data.get("original_description")
    original_deadline = data.get("original_deadline")
    deadline_str = deadline.strftime("%d.%m.%Y")

    attachment_changed = (attachment or {}) != (original_attachment or {})
    content_changed = attachment_changed or (description or "") != (original_description or "")
    deadline_changed = deadline_str != (original_deadline or "")

    if not content_changed and not deadline_changed:
        await state.clear()
        await restore_admin_view(
            message.bot,
            db,
            data.get("admin_origin_chat_id"),
            data.get("admin_origin_message_id"),
            data.get("admin_return_view"),
        )
        await message.answer(
            "ℹ️ Изменений не было, домашнее задание осталось прежним.",
            reply_markup=make_back_button_keyboard("◀️ К активным ДЗ", data.get("admin_return_view") or "admin:all_homework"),
        )
        return

    try:
        await db.update_homework(
            data["homework_id"],
            data["student_id"],
            title,
            description,
            deadline,
            attachment=attachment,
        )
    except Exception as exc:
        logger.error("Ошибка обновления ДЗ %s: %s", data.get("homework_id"), exc)
        await message.answer(
            "⚠️ Не удалось обновить ДЗ. Попробуйте ещё раз.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    homework_html = homework_body_html(
        title,
        description,
        (attachment or {}).get("file_name"),
        (attachment or {}).get("mime_type"),
    ) or "—"

    await state.clear()
    await restore_admin_view(
        message.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )

    try:
        if attachment_changed and attachment and attachment.get("file_id"):
            await message.bot.send_document(
                data["student_id"],
                attachment["file_id"],
            )
        await message.bot.send_message(
            data["student_id"],
            f"📚 <b>Домашнее задание обновлено!</b>\n\n"
            f"📝 Задание:\n{homework_html}\n"
            f"📅 Дедлайн: <b>{deadline_str}</b>",
            reply_markup=make_teacher_reply_keyboard("homework", data["homework_id"]),
        )
    except Exception as exc:
        logger.warning("Не удалось отправить обновлённое ДЗ ученику %s: %s", data["student_id"], exc)

    student_name = q(data.get("student_name") or data["student_id"])
    await message.answer(
        f"✅ <b>Домашнее задание обновлено</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"📝 Задание:\n{homework_html}\n"
        f"📅 Дедлайн: {deadline_str}\n\n"
        "Список активных ДЗ уже обновлён.",
        reply_markup=make_back_button_keyboard("◀️ К активным ДЗ", data.get("admin_return_view") or "admin:all_homework"),
    )


@router.callback_query(lambda c: c.data.startswith('admin:add_homework'))
async def admin_add_homework_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_REGISTERED_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard
        )
        await callback_query.answer()
        return
    await state.clear()
    await state.update_data(
        admin_return_view=_return_view_from_source(source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddHomework.waiting_for_student)
    await render_admin_student_picker(callback_query.message, db, flow="add_homework", page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:quick:add_homework:'))
async def admin_add_homework_quick(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    student_id_str = parts[3]
    page_str = parts[4]
    source = parts[5] if len(parts) > 5 else "card"
    student_id = int(student_id_str)
    page = int(page_str)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)

    await state.clear()
    await state.update_data(
        student_id=student_id,
        admin_return_view=_student_return_view(student_id, page, source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await _prompt_for_homework_description(callback_query.message, state, db, student_id)
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:') or c.data.startswith("admin:student_pick_select:add_homework:"),
    StateFilter(AdminAddHomework.waiting_for_student),
)
async def admin_hw_student_selected(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if callback_query.data.startswith("admin:student_pick_select:"):
        _, student_id, _ = parse_admin_student_picker_callback_data(callback_query.data)
    else:
        student_id = int(callback_query.data.split(':')[1])
    await state.update_data(student_id=student_id)
    await _prompt_for_homework_description(callback_query.message, state, db, student_id)
    await callback_query.answer()


@router.message(StateFilter(AdminAddHomework.waiting_for_description))
async def admin_hw_description_entered(message: types.Message, state: FSMContext):
    payload = extract_homework_payload(message)
    if not payload:
        await message.answer(
            ADMIN_ADD_HOMEWORK_EMPTY_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return
    await state.update_data(
        title="",
        description=payload["description"],
        attachment=payload["attachment"],
    )
    await state.set_state(AdminAddHomework.waiting_for_deadline)
    await message.answer(
        ADMIN_ADD_HOMEWORK_DEADLINE_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(AdminAddHomework.waiting_for_deadline))
async def admin_hw_deadline_entered(message: types.Message, state: FSMContext, db: Database):
    raw_deadline = (message.text or "").strip().replace("/", ".").replace("\\", ".")
    try:
        deadline = datetime.strptime(raw_deadline, "%d.%m.%Y")
    except ValueError:
        await message.answer(
            ADMIN_ADD_HOMEWORK_DEADLINE_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    attachment = data.get("attachment")
    return_view = data.get("admin_return_view")
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")
    try:
        homework_id = await db.add_homework(
            data['student_id'],
            data['title'],
            data.get('description'),
            deadline,
            attachment=attachment,
        )
    except Exception as exc:
        logger.error("Ошибка сохранения ДЗ: %s", exc)
        await message.answer(
            "⚠️ Не удалось сохранить ДЗ. Попробуйте ещё раз или отправьте текст короче.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    student = await db.get_user(data['student_id'])
    student_name = q(student['full_name']) if student else str(data['student_id'])
    homework_html = homework_body_html(
        data.get('title'),
        data.get('description'),
        (attachment or {}).get('file_name'),
        (attachment or {}).get('mime_type'),
    ) or "—"

    await state.clear()
    await restore_admin_view(message.bot, db, origin_chat_id, origin_message_id, return_view)

    try:
        if attachment and attachment.get("file_id"):
            await message.bot.send_document(
                data['student_id'],
                attachment["file_id"],
            )
        await message.bot.send_message(
            data['student_id'],
            f"📚 <b>Новое домашнее задание!</b>\n\n"
            f"📝 Задание:\n{homework_html}\n"
            f"📅 Дедлайн: <b>{deadline.strftime('%d.%m.%Y')}</b>",
            reply_markup=make_teacher_reply_keyboard("homework", homework_id),
        )
    except Exception as exc:
        logger.warning("Не удалось отправить ДЗ ученику %s: %s", data['student_id'], exc)

    await message.answer(
        f"✅ <b>Домашнее задание отправлено</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"📝 Задание:\n{homework_html}\n"
        f"📅 Дедлайн: {deadline.strftime('%d.%m.%Y')}\n\n"
        "Карточка ученика и список ДЗ уже обновлены.",
        reply_markup=_reply_markup_for_return_view(return_view, data['student_id']),
    )


@router.callback_query(lambda c: c.data == 'admin:all_homework')
async def admin_all_homework(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_homework_list(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:homework_manage:'))
async def admin_homework_manage(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    hw_id = int(callback_query.data.split(':')[2])
    await _render_admin_homework_manage(callback_query.message, db, hw_id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('hw_edit_start:'))
async def admin_homework_edit_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    hw_id = int(callback_query.data.split(':')[1])
    hw = await db.get_homework_by_id(hw_id)
    if not hw:
        await callback_query.message.edit_text(
            "⚠️ Домашнее задание не найдено.",
            reply_markup=make_back_button_keyboard("◀️ К активным ДЗ", "admin:all_homework"),
        )
        await callback_query.answer()
        return

    student = await db.get_user(hw["student_id"])
    student_name = student["full_name"] if student else str(hw["student_id"])
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    attachment = _homework_attachment_payload(hw)
    await state.clear()
    await state.update_data(
        homework_id=hw_id,
        student_id=hw["student_id"],
        student_name=student_name,
        title=hw.get("title") or "",
        description=hw.get("description"),
        attachment=attachment,
        original_description=hw.get("description"),
        original_attachment=attachment,
        original_deadline=_deadline_label(hw.get("deadline")),
        admin_return_view="admin:all_homework",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminEditHomework.waiting_for_description)
    await callback_query.message.edit_text(
        _build_homework_edit_description_prompt(student_name, hw),
        reply_markup=make_homework_edit_content_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'hw_edit_keep_content', StateFilter(AdminEditHomework.waiting_for_description))
async def admin_homework_edit_keep_content(callback_query: types.CallbackQuery, state: FSMContext):
    await _prompt_for_homework_edit_deadline(callback_query.message, state)
    await callback_query.answer()


@router.message(StateFilter(AdminEditHomework.waiting_for_description))
async def admin_homework_edit_description_entered(message: types.Message, state: FSMContext):
    payload = extract_homework_payload(message)
    if not payload:
        await message.answer(
            ADMIN_ADD_HOMEWORK_EMPTY_TEXT,
            reply_markup=make_homework_edit_content_keyboard(),
        )
        return

    data = await state.get_data()
    description = payload["description"] if payload["description"] else data.get("original_description")
    attachment = payload["attachment"] if payload["attachment"] else data.get("original_attachment")
    await state.update_data(
        description=description,
        attachment=attachment,
    )
    await state.set_state(AdminEditHomework.waiting_for_deadline)
    await message.answer(
        _build_homework_edit_deadline_prompt(
            data.get("student_name") or str(data.get("student_id") or "—"),
            description,
            attachment,
            data.get("original_deadline") or "—",
        ),
        reply_markup=make_homework_edit_deadline_keyboard(data.get("original_deadline") or "—"),
    )


@router.callback_query(lambda c: c.data == 'hw_edit_keep_deadline', StateFilter(AdminEditHomework.waiting_for_deadline))
async def admin_homework_edit_keep_deadline(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    data = await state.get_data()
    try:
        deadline = _parse_homework_deadline(data.get("original_deadline"))
    except ValueError:
        await callback_query.answer("Не удалось сохранить текущий дедлайн.", show_alert=True)
        return

    await _finish_homework_edit(callback_query.message, state, db, deadline)
    await callback_query.answer()


@router.message(StateFilter(AdminEditHomework.waiting_for_deadline))
async def admin_homework_edit_deadline_entered(message: types.Message, state: FSMContext, db: Database):
    try:
        deadline = _parse_homework_deadline(message.text)
    except ValueError:
        await message.answer(
            ADMIN_ADD_HOMEWORK_DEADLINE_INVALID_TEXT,
            reply_markup=make_homework_edit_deadline_keyboard((await state.get_data()).get("original_deadline") or "—"),
        )
        return

    await _finish_homework_edit(message, state, db, deadline)


@router.callback_query(lambda c: c.data.startswith('hw_delete_confirm:'))
async def admin_homework_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    hw_id = int(callback_query.data.split(':')[1])
    hw = await db.get_homework_by_id(hw_id)

    if not hw:
        await callback_query.message.edit_text(
            "⚠️ Домашнее задание не найдено.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    student = await db.get_user(hw['student_id'])
    student_name = q(student['full_name']) if student else str(hw['student_id'])
    deadline_str = hw['deadline'].strftime('%d.%m.%Y') if hw.get('deadline') else '—'
    homework_html = homework_body_html(
        hw.get('title'),
        hw.get('description'),
        hw.get('attachment_name'),
        hw.get('attachment_mime_type'),
    ) or "—"
    await callback_query.message.edit_text(
        "🗑 <b>Удалить домашнее задание?</b>\n\n"
        f"👤 Ученик: <b>{student_name}</b>\n"
        f"📝 Задание:\n{homework_html}\n"
        f"📅 Дедлайн: <b>{deadline_str}</b>\n\n"
        "⚠️ Действие необратимо.",
        reply_markup=make_homework_delete_confirm_keyboard(hw_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('hw_delete:'))
async def admin_homework_delete(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    hw_id = int(callback_query.data.split(':')[1])
    hw = await db.get_homework_by_id(hw_id)

    if not hw:
        await callback_query.message.edit_text(
            "⚠️ Домашнее задание уже удалено.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await db.delete_homework(hw_id)
    await _render_admin_homework_list(callback_query.message, db)
    await callback_query.answer("ДЗ удалено.")
