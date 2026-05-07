"""Global navigation, main menu, and study plan callbacks."""
import logging

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from data.config import load_teacher_info
from handlers.users.admin_sections.common import restore_admin_view
from handlers.users.screens import render_profile_screen, render_user_home
from handlers.users._cb_helpers import (
    _edit_text_for_actor,
    _get_learning_student_id,
    _resolve_actor_context,
    _block_preview_action,
)
from keyboards.inline import (
    back_to_menu_keyboard,
    back_to_admin_keyboard,
    make_homework_filter_keyboard,
    make_homework_list_keyboard,
    make_homework_item_keyboard,
    make_notifications_keyboard,
    make_schedule_keyboard,
    make_study_plan_keyboard,
    payment_keyboard,
    freeze_keyboard,
)
from utils.db_api.postgresql import Database
from utils.homework_text import homework_body_html
from utils.ui_text import (
    ACTION_CANCELLED_TEXT,
    REGISTRATION_REQUIRED_TEXT,
    build_action_result_text,
    build_freeze_intro_text,
    build_homework_text,
    build_notifications_text,
    build_payment_text,
    build_schedule_text,
    build_study_plan_text,
)

logger = logging.getLogger(__name__)

router = Router()


async def _render_notifications_screen(message: types.Message, db: Database, user_id: int, preview: dict | None = None):
    user = await db.get_user(user_id)
    reminders = (user.get("lesson_reminders") or "enabled") if user else "enabled"
    await _edit_text_for_actor(
        message,
        build_notifications_text(reminders),
        make_notifications_keyboard(reminders),
        preview,
    )


async def _render_homework_list(message: types.Message, db: Database, user_id: int, status: str = "active", preview: dict | None = None):
    learning_user_id = await _get_learning_student_id(db, user_id)
    items = await db.get_student_homework(learning_user_id, status)
    learning_user = await db.get_user(learning_user_id) if learning_user_id else None
    homework_exempt = bool(learning_user.get("homework_exempt")) if learning_user else False
    await _edit_text_for_actor(
        message,
        build_homework_text(items, status, homework_exempt=homework_exempt),
        make_homework_list_keyboard(items, status) if items else make_homework_filter_keyboard(status),
        preview,
    )


async def _render_homework_detail(message: types.Message, db: Database, user_id: int, hw_id: int, status: str, preview: dict | None = None):
    learning_user_id = await _get_learning_student_id(db, user_id)
    hw = await db.get_homework_by_id(hw_id)
    if not hw or hw["student_id"] != learning_user_id or (status and hw["status"] != status):
        await _edit_text_for_actor(
            message,
            "ℹ️ Задание не найдено или уже недоступно.",
            back_to_menu_keyboard,
            preview,
        )
        return

    homework_html = homework_body_html(
        hw.get("title"),
        hw.get("description"),
        hw.get("attachment_name"),
        hw.get("attachment_mime_type"),
    ) or "—"
    title = "📚 <b>Домашнее задание</b>" if status == "active" else "✅ <b>Выполненное задание</b>"
    await _edit_text_for_actor(
        message,
        "\n".join([
            title,
            "",
            homework_html,
            f"📅 Дедлайн: <b>{hw['deadline'].strftime('%d.%m.%Y') if hw.get('deadline') else '—'}</b>",
        ]),
        make_homework_item_keyboard(hw_id, status, has_attachment=bool(hw.get("attachment_file_id"))),
        preview,
    )


async def _render_study_plan(
    message: types.Message,
    db: Database,
    user_id: int,
    preview: dict | None = None,
    *,
    parent_link_id: int | None = None,
):
    learning_user_id = await _get_learning_student_id(db, user_id)
    user = await db.get_user(user_id)
    if not user:
        await _edit_text_for_actor(message, REGISTRATION_REQUIRED_TEXT, back_to_menu_keyboard, preview)
        return

    plan = await db.get_active_learning_plan(learning_user_id)
    checklist = await db.ensure_study_plan_checklist(learning_user_id)
    homework = list(await db.get_student_homework(learning_user_id, "active") or [])
    pair = None
    get_pair = getattr(db, "get_student_pair_for_student", None)
    if callable(get_pair):
        pair = await get_pair(learning_user_id)

    await _edit_text_for_actor(
        message,
        build_study_plan_text(
            user,
            plan,
            checklist.get("lesson"),
            homework,
            list(checklist.get("items") or []),
            pair=pair,
        ),
        make_study_plan_keyboard(plan, list(checklist.get("items") or []), parent_link_id=parent_link_id),
        preview,
    )


@router.callback_query(lambda c: c.data == 'back_to_menu', StateFilter('*'))
async def back_to_menu(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'cancel_fsm', StateFilter('*'))
async def cancel_fsm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    from utils.preview_mode import get_preview_context
    state_data = await state.get_data()
    await state.clear()
    is_admin = callback_query.from_user.id == config.ADMIN_ID
    preview = await get_preview_context(db, callback_query.from_user.id)
    if is_admin:
        restored = await restore_admin_view(
            callback_query.bot,
            db,
            state_data.get("admin_origin_chat_id"),
            state_data.get("admin_origin_message_id"),
            state_data.get("admin_return_view"),
        )
        if restored:
            await callback_query.answer("Действие отменено.")
            return
        if preview:
            await render_user_home(callback_query.message, db, callback_query.from_user.id)
            await callback_query.answer("Действие отменено.")
            return
    await callback_query.message.edit_text(
        ACTION_CANCELLED_TEXT,
        reply_markup=back_to_admin_keyboard if is_admin else back_to_menu_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data in ['schedule', 'freeze', 'payment', 'profile'])
async def process_menu_choice(callback_query: types.CallbackQuery, db: Database):
    choice = callback_query.data
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)

    if not user:
        await _edit_text_for_actor(
            callback_query.message,
            REGISTRATION_REQUIRED_TEXT,
            back_to_menu_keyboard,
            preview,
        )
        await callback_query.answer()
        return

    user_role = user.get("role")
    if choice in ('schedule', 'freeze', 'payment') and user_role and user_role != "student":
        await callback_query.answer(
            "Этот раздел доступен только ученикам. Откройте кабинет ребёнка через «Мои дети».",
            show_alert=True,
        )
        return

    learning_user_id = await _get_learning_student_id(db, user_id) if user.get("role") == "student" else user_id

    if choice == 'schedule':
        lessons = await db.get_active_lessons(learning_user_id)
        text = build_schedule_text(lessons, lesson_format=user.get("lesson_format"))
        info = load_teacher_info()
        calendar_url = info.get('contacts', {}).get('calendar_url', '')
        await _edit_text_for_actor(
            callback_query.message,
            text,
            make_schedule_keyboard(calendar_url),
            preview,
        )

    elif choice == 'freeze':
        lessons = await db.get_active_lessons(learning_user_id)
        active_count = len(lessons)
        if not active_count:
            await _edit_text_for_actor(
                callback_query.message,
                build_action_result_text(
                    "Заморозка сейчас не нужна",
                    "У вас нет активных занятий, которые можно отправить на заморозку.",
                    next_step="Когда появятся новые уроки, к этой кнопке можно будет вернуться в любой момент.",
                    icon="ℹ️",
                ),
                back_to_menu_keyboard,
                preview,
            )
        else:
            await _edit_text_for_actor(
                callback_query.message,
                build_freeze_intro_text(active_count),
                freeze_keyboard,
                preview,
            )

    elif choice == 'payment':
        if user and user.get("student_type") == "schoolchild":
            await _edit_text_for_actor(
                callback_query.message,
                "💰 Информация об оплате доступна в кабинете родителя.",
                back_to_menu_keyboard,
                preview,
            )
        else:
            balance = await db.get_student_lesson_balance(learning_user_id)
            transactions = list(await db.get_student_transactions(learning_user_id) or [])
            text = build_payment_text(balance, [], transactions=transactions)
            await _edit_text_for_actor(callback_query.message, text, payment_keyboard, preview)

    elif choice == 'profile':
        await render_profile_screen(callback_query.message, db, callback_query.from_user.id)

    await callback_query.answer()


@router.callback_query(lambda c: c.data == "study_plan")
async def process_study_plan(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "student":
        await callback_query.answer("Учебный план доступен ученикам.", show_alert=True)
        return
    await _render_study_plan(callback_query.message, db, user_id, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("study_plan:file:"))
async def process_study_plan_file(callback_query: types.CallbackQuery, db: Database):
    user_id, user, _ = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "student":
        await callback_query.answer("Учебный план доступен ученикам.", show_alert=True)
        return
    learning_user_id = await _get_learning_student_id(db, user_id)
    plan_id = int(callback_query.data.split(":")[2])
    plan = await db.get_learning_plan_by_id(plan_id)
    if not plan or plan.get("student_id") != learning_user_id or plan.get("status") != "active":
        await callback_query.answer("PDF-план не найден.", show_alert=True)
        return
    await callback_query.bot.send_document(callback_query.from_user.id, plan["file_id"])
    await callback_query.answer("PDF отправлен.")


@router.callback_query(lambda c: c.data.startswith("study_plan:toggle:"))
async def process_study_plan_toggle(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return
    user_id = callback_query.from_user.id
    learning_user_id = await _get_learning_student_id(db, user_id)
    item_id = int(callback_query.data.split(":")[2])
    item = await db.toggle_study_plan_checklist_item(item_id, learning_user_id)
    if not item:
        await callback_query.answer("Пункт не найден.", show_alert=True)
        return
    await _render_study_plan(callback_query.message, db, user_id)
    await callback_query.answer("Готово.")
