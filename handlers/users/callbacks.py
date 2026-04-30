import logging

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from data.config import load_teacher_info
from handlers.users.admin_sections.common import restore_admin_view
from handlers.users.screens import render_profile_screen, render_user_home
from keyboards.inline import (
    freeze_keyboard, back_to_menu_keyboard, back_to_admin_keyboard,
    cancel_fsm_keyboard, make_freeze_confirm_keyboard, FREEZE_REASON_LABELS,
    payment_keyboard, make_homework_filter_keyboard,
    make_homework_item_keyboard, make_homework_list_keyboard, make_contacts_keyboard,
    make_materials_keyboard, make_notifications_keyboard, profile_keyboard,
    make_parent_child_keyboard, make_parent_homework_keyboard, make_parent_homework_item_keyboard,
    make_parent_payments_keyboard, make_level_test_link_keyboard, make_profile_danger_keyboard,
    make_schedule_keyboard, make_self_delete_confirm_keyboard, make_self_delete_review_keyboard,
    make_teacher_reply_keyboard, make_write_to_student_keyboard, make_back_button_keyboard,
    make_study_plan_keyboard,
)
from states.registration import FreezeConfirm, StudentReply
from utils.db_api.postgresql import Database
from utils.homework_text import homework_body_html, homework_preview_text
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
from utils.reschedule import decode_reschedule_slot, format_reschedule_slot_label
from utils.time import business_today
from utils.ui_text import (
    ACTION_CANCELLED_TEXT,
    REGISTRATION_REQUIRED_TEXT,
    build_action_result_text,
    build_contacts_text,
    build_freeze_confirm_text,
    build_freeze_intro_text,
    build_freeze_success_text,
    build_homework_text,
    build_materials_text,
    build_notifications_text,
    build_parent_child_hub_text,
    build_payment_text,
    build_requisites_text,
    build_schedule_text,
    build_self_delete_final_warning_text,
    build_self_delete_success_text,
    build_self_delete_warning_text,
    build_study_plan_text,
)

logger = logging.getLogger(__name__)

router = Router()

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


# ─── Global navigation ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'back_to_menu', StateFilter('*'))
async def back_to_menu(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'cancel_fsm', StateFilter('*'))
async def cancel_fsm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
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


# ─── Main menu callbacks ──────────────────────────────────────────────────────


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
    await _edit_text_for_actor(
        message,
        build_homework_text(items, status),
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


async def _render_parent_child_home(message: types.Message, db: Database, parent_id: int, link_id: int, preview: dict | None = None):
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await _edit_text_for_actor(
            message,
            "⚠️ Не удалось найти этого ребёнка в вашем кабинете.",
            back_to_menu_keyboard,
            preview,
        )
        return
    await _edit_text_for_actor(
        message,
        build_parent_child_hub_text(child),
        make_parent_child_keyboard(link_id, linked=child.get("link_status") == "linked"),
        preview,
    )


async def _render_parent_homework_detail(
    message: types.Message,
    db: Database,
    parent_id: int,
    link_id: int,
    hw_id: int,
    status: str,
    preview: dict | None = None,
):
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    hw = await db.get_homework_by_id(hw_id)
    if (
        not child
        or child.get("link_status") != "linked"
        or not hw
        or hw.get("student_id") != child.get("student_id")
        or (status and hw.get("status") != status)
    ):
        await _edit_text_for_actor(
            message,
            "ℹ️ Задание не найдено или уже недоступно.",
            make_back_button_keyboard("◀️ К ребёнку", f"parent:child:{link_id}"),
            preview,
        )
        return

    homework_html = homework_body_html(
        hw.get("title"),
        hw.get("description"),
        hw.get("attachment_name"),
        hw.get("attachment_mime_type"),
    ) or "—"
    title = "📚 <b>Домашнее задание ребёнка</b>" if status == "active" else "✅ <b>Выполненное задание ребёнка</b>"
    await _edit_text_for_actor(
        message,
        "\n".join([
            title,
            "",
            homework_html,
            f"📅 Дедлайн: <b>{hw['deadline'].strftime('%d.%m.%Y') if hw.get('deadline') else '—'}</b>",
        ]),
        make_parent_homework_item_keyboard(
            link_id,
            hw_id,
            status,
            has_attachment=bool(hw.get("attachment_file_id")),
        ),
        preview,
    )

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
        payments = await db.get_student_payments(learning_user_id)
        balance = await db.get_student_lesson_balance(learning_user_id)
        text = build_payment_text(balance, payments)
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


@router.callback_query(lambda c: c.data == "parent:home")
async def process_parent_home(callback_query: types.CallbackQuery, db: Database):
    _, user, _ = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:") and c.data.endswith(":schedule"))
async def process_parent_child_schedule(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    if child.get("link_status") != "linked":
        await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview)
        await callback_query.answer()
        return
    lessons = await _get_parent_child_schedule(db, parent_id, link_id, preview)
    await _edit_text_for_actor(
        callback_query.message,
        build_schedule_text(list(lessons or []), lesson_format=child.get("lesson_format")),
        make_back_button_keyboard("◀️ К ребёнку", f"parent:child:{link_id}"),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:") and ":homework:view:" in c.data)
async def process_parent_child_homework_detail(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    parts = callback_query.data.split(":")
    if len(parts) != 7:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    link_id = int(parts[2])
    hw_id = int(parts[5])
    status = parts[6]
    await _render_parent_homework_detail(callback_query.message, db, parent_id, link_id, hw_id, status, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:") and ":homework:file:" in c.data)
async def process_parent_child_homework_file(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    parent_id = callback_query.from_user.id
    parts = callback_query.data.split(":")
    if len(parts) != 7:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return

    link_id = int(parts[2])
    hw_id = int(parts[5])
    status = parts[6]
    child = await db.get_parent_child_link(parent_id, link_id)
    hw = await db.get_homework_by_id(hw_id)
    if (
        not child
        or child.get("link_status") != "linked"
        or not hw
        or hw.get("student_id") != child.get("student_id")
        or (status and hw.get("status") != status)
    ):
        await callback_query.answer("Задание не найдено или уже недоступно.", show_alert=True)
        return
    if not hw.get("attachment_file_id"):
        await callback_query.answer("У этого задания нет вложенного файла.", show_alert=True)
        return

    try:
        await callback_query.bot.send_document(parent_id, hw["attachment_file_id"])
    except Exception:
        await callback_query.answer("Не удалось отправить файл. Попробуйте чуть позже.", show_alert=True)
        return

    await callback_query.answer("Файл отправлен.")


@router.callback_query(
    lambda c: c.data.startswith("parent:child:")
    and (c.data.endswith(":homework:active") or c.data.endswith(":homework:done"))
)
async def process_parent_child_homework(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    parts = callback_query.data.split(":")
    link_id = int(parts[2])
    status = parts[4]
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    if child.get("link_status") != "linked":
        await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview)
        await callback_query.answer()
        return
    items = await _get_parent_child_homework(db, parent_id, link_id, status, preview)
    await _edit_text_for_actor(
        callback_query.message,
        build_homework_text(list(items or []), status),
        make_parent_homework_keyboard(link_id, status=status, items=list(items or [])),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:") and c.data.endswith(":payments"))
async def process_parent_child_payments(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    if child.get("link_status") != "linked":
        await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview)
        await callback_query.answer()
        return
    payments = await _get_parent_child_payments(db, parent_id, link_id, 20, preview)
    balance = int(child.get("lesson_balance") or 0)
    await _edit_text_for_actor(
        callback_query.message,
        build_payment_text(balance, list(payments or [])),
        make_parent_payments_keyboard(link_id),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:") and c.data.endswith(":study_plan"))
async def process_parent_child_study_plan(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child or child.get("link_status") != "linked":
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    await _render_study_plan(
        callback_query.message,
        db,
        int(child["student_id"]),
        preview=preview,
        parent_link_id=link_id,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:") and ":study_plan:file:" in c.data)
async def process_parent_child_study_plan_file(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    parts = callback_query.data.split(":")
    link_id = int(parts[2])
    plan_id = int(parts[-1])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child or child.get("link_status") != "linked":
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    learning_user_id = await _get_learning_student_id(db, int(child["student_id"]))
    plan = await db.get_learning_plan_by_id(plan_id)
    if not plan or plan.get("student_id") != learning_user_id or plan.get("status") != "active":
        await callback_query.answer("PDF-план не найден.", show_alert=True)
        return
    await callback_query.bot.send_document(callback_query.from_user.id, plan["file_id"])
    await callback_query.answer("PDF отправлен.")


@router.callback_query(lambda c: c.data.startswith("parent:child:") and c.data.endswith(":requisites"))
async def process_parent_child_requisites(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child or child.get("link_status") != "linked":
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    info = load_teacher_info()
    learning_user_id = await _get_learning_student_id(db, int(child["student_id"]))
    pricing_context = await db.get_student_pricing_context(learning_user_id)
    await _edit_text_for_actor(
        callback_query.message,
        build_requisites_text(info.get("requisites", {}), pricing_context),
        make_back_button_keyboard("◀️ К оплате", f"parent:child:{link_id}:payments"),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("parent:child:"))
async def process_parent_child_home(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    parts = callback_query.data.split(":")
    if len(parts) != 3:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    link_id = int(parts[2])
    await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview)
    await callback_query.answer()


async def _build_reply_context_label(db: Database, context_key: str, entity_id: int | None) -> str:
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
    entity_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if user["role"] == "parent" and context_key not in {"general", "payment"}:
        await callback_query.answer("Этот тип ответа сейчас доступен только ученикам.", show_alert=True)
        return
    context_label = await _build_reply_context_label(db, context_key, entity_id)

    await state.clear()
    await state.set_state(StudentReply.waiting_for_message)
    await state.update_data(
        reply_context_key=context_key,
        reply_entity_id=entity_id,
        reply_context_label=context_label,
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

    await state.clear()
    await message.answer(
        build_action_result_text(
            "Сообщение отправлено",
            "Преподаватель получит его в ближайшее время.",
            next_step="Если нужно, можно вернуться в меню и продолжить работу с ботом.",
        ),
        reply_markup=back_to_menu_keyboard,
    )


# ─── Contacts ─────────────────────────────────────────────────────────────────

def _build_contacts_text(info: dict, show_address: bool = False) -> str:
    return build_contacts_text(info, show_address=show_address)


def _get_level_test_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("level_test_url", "") or info.get("level_test_url", "")


def _get_project_site_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("project_site_url", "") or info.get("project_site_url", "")


def _get_materials_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return (
        contacts.get("materials_url", "")
        or contacts.get("filen_url", "")
        or info.get("materials_url", "")
        or info.get("filen_url", "")
    )


@router.callback_query(lambda c: c.data == 'contacts')
async def process_contacts(callback_query: types.CallbackQuery, db: Database):
    info = load_teacher_info()
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    text = _build_contacts_text(info, show_address=bool(user))
    contacts = info.get('contacts', {})
    kb = make_contacts_keyboard(
        booking_url=contacts.get('booking_url', ''),
        vk_call_url=contacts.get('vk_call', ''),
        google_meet_url=contacts.get('google_meet', ''),
        website_url=_get_project_site_url(info),
    )
    await _edit_text_for_actor(callback_query.message, text, kb, preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'materials')
async def process_materials(callback_query: types.CallbackQuery, db: Database):
    info = load_teacher_info()
    _, _, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    materials_url = _get_materials_url(info)
    website_url = _get_project_site_url(info)
    await _edit_text_for_actor(
        callback_query.message,
        build_materials_text(materials_url=materials_url, website_url=website_url),
        make_materials_keyboard(materials_url=materials_url, website_url=website_url),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('level_test:'))
async def process_level_test_choice(callback_query: types.CallbackQuery, db: Database):
    action = callback_query.data.split(':', 1)[1]
    url = _get_level_test_url()
    preview = await get_preview_context(db, callback_query.from_user.id)

    if action == "now":
        if url:
            await _edit_text_for_actor(
                callback_query.message,
                build_action_result_text(
                    "Тест уровня",
                    "Отлично. Откройте тест по кнопке ниже, когда будете готовы.",
                    next_step="Если что-то будет непонятно, можно написать преподавателю.",
                    icon="🧪",
                ),
                make_level_test_link_keyboard(url, back_callback="profile"),
                preview,
            )
        else:
            await _edit_text_for_actor(
                callback_query.message,
                build_action_result_text(
                    "Тест уровня",
                    "Ссылка на тест пока не добавлена.",
                    next_step="Напишите преподавателю, и он пришлёт её отдельно.",
                    icon="🧪",
                ),
                make_back_button_keyboard("◀️ Назад в профиль", "profile"),
                preview,
            )
    elif action == "later":
        await _edit_text_for_actor(
            callback_query.message,
            build_action_result_text(
                "Можно пройти позже",
                "Кнопка <b>🧪 Тест уровня</b> останется в профиле.",
                next_step="Когда захотите, вернитесь к ней в любое время.",
                icon="🕒",
            ),
            make_back_button_keyboard("◀️ Назад в профиль", "profile"),
            preview,
        )
    else:
        await _edit_text_for_actor(
            callback_query.message,
            build_action_result_text(
                "Тест можно не проходить",
                "Ничего страшного. Если передумаете, преподаватель поможет с выбором следующего шага.",
                icon="🙏",
            ),
            make_back_button_keyboard("◀️ Назад в профиль", "profile"),
            preview,
        )

    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'profile:danger')
async def process_profile_danger(callback_query: types.CallbackQuery, db: Database):
    _, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") not in {"student", "parent"}:
        await _edit_text_for_actor(
            callback_query.message,
            "ℹ️ Опасные действия доступны только ученикам и родителям.",
            back_to_menu_keyboard,
            preview,
        )
        await callback_query.answer()
        return

    await _edit_text_for_actor(
        callback_query.message,
        "🛡 <b>Опасные действия</b>\n\n"
        "Здесь находятся действия, которые удаляют профиль или доступ к данным.\n"
        "Используйте их только если уверены.",
        make_profile_danger_keyboard(),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'profile:delete_me')
async def process_profile_delete_me(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user:
        await _edit_text_for_actor(
            callback_query.message,
            "⚠️ Вы не зарегистрированы. Используйте /start.",
            back_to_menu_keyboard,
            preview,
        )
        await callback_query.answer()
        return

    if user["role"] not in {"student", "parent"}:
        await _edit_text_for_actor(
            callback_query.message,
            "ℹ️ Самоудаление сейчас доступно ученикам и родителям.",
            back_to_menu_keyboard,
            preview,
        )
        await callback_query.answer()
        return

    snapshot = await db.get_user_deletion_snapshot(user_id)
    await _edit_text_for_actor(
        callback_query.message,
        _build_self_delete_warning(user, snapshot),
        make_self_delete_review_keyboard(back_callback="profile:danger"),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'self_delete:review')
async def process_self_delete_review(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user:
        await _edit_text_for_actor(
            callback_query.message,
            "⚠️ Вы не зарегистрированы. Используйте /start.",
            back_to_menu_keyboard,
            preview,
        )
        await callback_query.answer()
        return

    await _edit_text_for_actor(
        callback_query.message,
        build_self_delete_final_warning_text(user.get("role")),
        make_self_delete_confirm_keyboard(back_callback="profile:delete_me"),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'self_delete:confirm')
async def process_self_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    user = await db.get_user(callback_query.from_user.id)
    if not user:
        await callback_query.message.edit_text(
            "⚠️ Профиль уже удалён. Используйте /start для новой регистрации.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    if user["role"] not in {"student", "parent"}:
        await callback_query.message.edit_text(
            "ℹ️ Самоудаление сейчас доступно ученикам и родителям.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    await db.delete_user_fully(callback_query.from_user.id)

    await callback_query.message.edit_text(
        build_self_delete_success_text(user["role"]),
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()


# ─── Requisites ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data in {'requisites', 'payment:requisites'})
async def process_requisites(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    back_keyboard = (
        make_back_button_keyboard("◀️ Назад к оплате", "payment")
        if callback_query.data == "payment:requisites"
        else back_to_menu_keyboard
    )

    if not user:
        await _edit_text_for_actor(
            callback_query.message,
            "🔒 Реквизиты доступны только зарегистрированным пользователям.\n\n"
            "Используйте /start для регистрации.",
            back_keyboard,
            preview,
        )
        await callback_query.answer()
        return

    info = load_teacher_info()
    pricing_context = None
    if user.get("role") == "student":
        learning_user_id = await _get_learning_student_id(db, user_id)
        pricing_context = await db.get_student_pricing_context(learning_user_id)
    await _edit_text_for_actor(
        callback_query.message,
        build_requisites_text(info.get("requisites", {}), pricing_context),
        back_keyboard,
        preview,
    )
    await callback_query.answer()


# ─── Freeze: two-step confirmation ───────────────────────────────────────────

@router.callback_query(lambda c: c.data.startswith('freeze:'))
async def process_freeze_reason(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if await _block_preview_action(callback_query, db, clear_state=state):
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

    await callback_query.message.edit_text(
        build_freeze_success_text(label, state_data.get("freeze_active_count", len(active))),
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()


# ─── Homework (student) ───────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'homework')
async def process_homework(callback_query: types.CallbackQuery, db: Database):
    user_id, _, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    await _render_homework_list(callback_query.message, db, user_id, status="active", preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data in ('hw:active', 'hw:done'))
async def process_homework_list(callback_query: types.CallbackQuery, db: Database):
    user_id, _, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    status = callback_query.data.split(':')[1]
    await _render_homework_list(callback_query.message, db, user_id, status=status, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("hw:view:"))
async def process_homework_detail(callback_query: types.CallbackQuery, db: Database):
    parts = callback_query.data.split(":")
    if len(parts) != 4:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    user_id, _, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    hw_id = int(parts[2])
    status = parts[3]
    await _render_homework_detail(callback_query.message, db, user_id, hw_id, status, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("hw:file:"))
async def process_homework_attachment(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    parts = callback_query.data.split(":")
    if len(parts) != 4:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return

    hw_id = int(parts[2])
    status = parts[3]
    user_id = callback_query.from_user.id
    learning_user_id = await _get_learning_student_id(db, user_id)
    hw = await db.get_homework_by_id(hw_id)
    if not hw or hw["student_id"] != learning_user_id or (status and hw["status"] != status):
        await callback_query.answer("Задание не найдено или уже недоступно.", show_alert=True)
        return
    if not hw.get("attachment_file_id"):
        await callback_query.answer("У этого задания нет вложенного файла.", show_alert=True)
        return

    try:
        await callback_query.bot.send_document(user_id, hw["attachment_file_id"])
    except Exception:
        await callback_query.answer("Не удалось отправить файл. Попробуйте чуть позже.", show_alert=True)
        return

    await callback_query.answer("Файл отправлен.")


@router.callback_query(lambda c: c.data.startswith('hw_done:'))
async def process_homework_done(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    user_id = callback_query.from_user.id
    learning_user_id = await _get_learning_student_id(db, user_id)
    hw_id = int(callback_query.data.split(':')[1])
    hw = await db.get_homework_by_id(hw_id)
    if not hw or hw['student_id'] != learning_user_id or hw['status'] != 'active':
        await callback_query.message.edit_text(
            "ℹ️ Задание не найдено или уже отмечено как выполненное.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    await db.mark_homework_done(hw_id, learning_user_id)
    homework_html = homework_body_html(
        hw.get("title"),
        hw.get("description"),
        hw.get("attachment_name"),
        hw.get("attachment_mime_type"),
    ) or "—"

    student = await db.get_user(user_id)
    student_name = html.quote(student['full_name']) if student else str(user_id)
    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"✅ <b>ДЗ выполнено!</b>\n\n"
                f"👤 {student_name}\n"
                f"📝 Задание:\n{homework_html}",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу уведомление о выполненном ДЗ %s: %s", hw_id, exc)

    await _render_homework_list(callback_query.message, db, user_id, status="active")
    await callback_query.answer("Отметил как выполненное.")


@router.callback_query(lambda c: c.data.startswith('lesson_presence:'))
async def process_lesson_presence(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Доступно только ученикам.", show_alert=True)
        return

    parts = callback_query.data.split(':')
    if len(parts) != 3 or parts[1] not in LESSON_PRESENCE_LABELS:
        await callback_query.answer("Некорректный ответ.", show_alert=True)
        return

    status = parts[1]
    lesson_id = int(parts[2]) if parts[2].isdigit() else None
    if not lesson_id:
        await callback_query.answer("Урок не найден.", show_alert=True)
        return

    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow("SELECT * FROM lessons WHERE id = $1", lesson_id)
    if not lesson or lesson["student_id"] != callback_query.from_user.id:
        await callback_query.answer("Этот урок недоступен.", show_alert=True)
        return

    lesson_time = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else "дата уточняется"
    student_name = html.quote(user["full_name"] or callback_query.from_user.full_name or str(callback_query.from_user.id))
    answer_label = LESSON_PRESENCE_LABELS[status]

    await callback_query.message.edit_text(
        build_action_result_text(
            "Ответ принят",
            f"Статус по занятию: <b>{answer_label}</b>.",
            next_step="Спасибо за подтверждение.",
        ),
        reply_markup=back_to_menu_keyboard,
    )

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"📩 <b>Ответ по занятию</b>\n\n"
                f"👤 Ученик: {student_name}\n"
                f"📅 Урок: <b>{lesson_time}</b>\n"
                f"Статус: <b>{answer_label}</b>",
                reply_markup=make_write_to_student_keyboard(callback_query.from_user.id),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу статус по занятию %s: %s", lesson_id, exc)

    await callback_query.answer("Ответ отправлен.")


@router.callback_query(lambda c: c.data.startswith('reschedule_pick:'))
async def process_reschedule_pick(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Доступно только ученикам.", show_alert=True)
        return

    token = callback_query.data.split(':', 1)[1]
    try:
        slot = decode_reschedule_slot(token)
    except ValueError:
        await callback_query.answer("Слот не распознан.", show_alert=True)
        return

    slot_label = format_reschedule_slot_label(slot)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Вариант переноса отправлен",
            f"Я передал преподавателю, что вам подходит <b>{html.quote(slot_label)}</b>.",
            next_step="Если нужно, можно ещё написать преподавателю вручную.",
        ),
        reply_markup=back_to_menu_keyboard,
    )

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                "🗓 <b>Выбран вариант переноса</b>\n\n"
                f"👤 Ученик: <b>{html.quote(user['full_name'])}</b>\n"
                f"📅 Предпочтительный слот: <b>{html.quote(slot_label)}</b>",
                reply_markup=make_write_to_student_keyboard(callback_query.from_user.id),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу выбранный слот переноса: %s", exc)

    await callback_query.answer("Вариант отправлен.")


# ─── Notifications settings ───────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'notif:manage')
async def process_notif_manage(callback_query: types.CallbackQuery, db: Database):
    user_id, _, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    await _render_notifications_screen(callback_query.message, db, user_id, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('notif:'))
async def process_notif_action(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    action = callback_query.data.split(':', 1)[1]
    user_id = callback_query.from_user.id

    from datetime import timedelta
    if action == 'disable':
        await db.set_lesson_reminders(user_id, 'disabled')
    elif action == 'pause_week':
        until = (business_today() + timedelta(weeks=1)).strftime('%d.%m.%Y')
        await db.set_lesson_reminders(user_id, f'paused_until:{until}')
    elif action == 'enable':
        await db.set_lesson_reminders(user_id, 'enabled')
    else:
        await callback_query.answer()
        return

    await _render_notifications_screen(callback_query.message, db, user_id)
    await callback_query.answer()
