import logging
from datetime import datetime

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_context_keyboard,
    make_back_button_keyboard,
    make_homework_delete_confirm_keyboard,
    make_homework_delete_keyboard,
    make_student_select_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import AdminAddHomework
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT,
    ADMIN_ADD_HOMEWORK_DEADLINE_INVALID_TEXT,
    ADMIN_ADD_HOMEWORK_DEADLINE_PROMPT_TEXT,
    ADMIN_ADD_HOMEWORK_EMPTY_TEXT,
    ADMIN_ADD_HOMEWORK_START_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    build_admin_homework_list_text,
)

from handlers.users.admin_sections.common import (
    get_message_origin,
    is_admin,
    message_to_html,
    q,
    restore_admin_view,
)

logger = logging.getLogger(__name__)
router = Router()


def _return_view_from_source(source: str | None) -> str:
    return "admin:cat:education" if source == "education" else "admin:home"


def _reply_markup_for_return_view(return_view: str | None, student_id: int | None = None):
    if return_view and return_view.startswith("admin:student_card:") and student_id is not None:
        parts = return_view.split(":")
        if len(parts) == 4:
            return make_admin_context_keyboard(student_id, int(parts[3]))
    return make_back_button_keyboard("◀️ Вернуться", return_view or "admin:home")


async def _render_admin_homework_list(message: types.Message, db: Database):
    items = await db.get_all_active_homework()
    await message.edit_text(
        build_admin_homework_list_text(items),
        reply_markup=make_homework_delete_keyboard(items) if items else make_back_button_keyboard("◀️ К учебному процессу", "admin:cat:education"),
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
    await callback_query.message.edit_text(
        ADMIN_ADD_HOMEWORK_START_TEXT,
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:quick:add_homework:'))
async def admin_add_homework_quick(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, _, student_id_str, page_str = callback_query.data.split(':')
    student_id = int(student_id_str)
    page = int(page_str)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)

    await state.clear()
    await state.update_data(
        student_id=student_id,
        admin_return_view=f"admin:student_card:{student_id}:{page}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddHomework.waiting_for_description)
    await callback_query.message.edit_text(
        ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:'),
    StateFilter(AdminAddHomework.waiting_for_student),
)
async def admin_hw_student_selected(callback_query: types.CallbackQuery, state: FSMContext):
    student_id = int(callback_query.data.split(':')[1])
    await state.update_data(student_id=student_id)
    await state.set_state(AdminAddHomework.waiting_for_description)
    await callback_query.message.edit_text(
        ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddHomework.waiting_for_description))
async def admin_hw_description_entered(message: types.Message, state: FSMContext):
    hw_raw = (message.text or "").strip()
    if not hw_raw:
        await message.answer(
            ADMIN_ADD_HOMEWORK_EMPTY_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return
    hw_text = message_to_html(message)
    if len(hw_text) > 240:
        short_title = html.quote(hw_raw[:117].strip()) + "..."
        await state.update_data(title=short_title, description=hw_text)
    else:
        await state.update_data(title=hw_text, description=None)
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
    return_view = data.get("admin_return_view")
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")
    try:
        homework_id = await db.add_homework(data['student_id'], data['title'], data.get('description'), deadline)
    except Exception as exc:
        logger.error("Ошибка сохранения ДЗ: %s", exc)
        await message.answer(
            "⚠️ Не удалось сохранить ДЗ. Попробуйте ещё раз или отправьте текст короче.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    student = await db.get_user(data['student_id'])
    student_name = q(student['full_name']) if student else str(data['student_id'])

    await state.clear()
    await restore_admin_view(message.bot, db, origin_chat_id, origin_message_id, return_view)

    desc_text = f"\n📄 {data['description']}" if data.get('description') else ""
    try:
        await message.bot.send_message(
            data['student_id'],
            f"📚 <b>Новое домашнее задание!</b>\n\n"
            f"📝 Задание: <b>{data['title']}</b>{desc_text}\n"
            f"📅 Дедлайн: <b>{deadline.strftime('%d.%m.%Y')}</b>",
            reply_markup=make_teacher_reply_keyboard("homework", homework_id),
        )
    except Exception as exc:
        logger.warning("Не удалось отправить ДЗ ученику %s: %s", data['student_id'], exc)

    await message.answer(
        f"✅ <b>Домашнее задание отправлено</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"📝 Задание: {q(data['title'])}\n"
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
    await callback_query.message.edit_text(
        "🗑 <b>Удалить домашнее задание?</b>\n\n"
        f"👤 Ученик: <b>{student_name}</b>\n"
        f"📝 Задание: <b>{q(hw['title'])}</b>\n"
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
