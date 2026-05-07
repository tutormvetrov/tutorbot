"""Parent/child dashboard callbacks."""
import logging

from aiogram import Router, types

from data.config import load_teacher_info
from handlers.users.screens import render_profile_screen, render_user_home
from handlers.users._cb_helpers import (
    _block_preview_action,
    _edit_text_for_actor,
    _get_learning_student_id,
    _get_parent_child_homework,
    _get_parent_child_link,
    _get_parent_child_payments,
    _get_parent_child_schedule,
    _resolve_actor_context,
    _resolve_engagement_mode,
)
from handlers.users.cb_navigation import _render_study_plan
from keyboards.inline import (
    back_to_menu_keyboard,
    make_back_button_keyboard,
    make_parent_child_keyboard,
    make_parent_homework_keyboard,
    make_parent_homework_item_keyboard,
    make_parent_payments_keyboard,
)
from utils.db_api.postgresql import Database
from utils.homework_text import homework_body_html
from utils.ui_text import (
    build_homework_text,
    build_parent_child_hub_text,
    build_payment_text,
    build_requisites_text,
    build_schedule_text,
)

logger = logging.getLogger(__name__)

router = Router()


async def _render_parent_child_home(
    message: types.Message,
    db: Database,
    parent_id: int,
    link_id: int,
    preview: dict | None = None,
    engagement_mode: str = "active",
):
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
        build_parent_child_hub_text(child, engagement_mode=engagement_mode),
        make_parent_child_keyboard(
            link_id,
            linked=child.get("link_status") == "linked",
            engagement_mode=engagement_mode,
        ),
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


@router.callback_query(lambda c: c.data == "parent:home")
async def process_parent_home(callback_query: types.CallbackQuery, db: Database):
    _, user, _ = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "parent:engagement:toggle")
async def process_parent_engagement_toggle(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return
    parent_id = callback_query.from_user.id
    user = await db.get_user(parent_id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    current = _resolve_engagement_mode(user)
    new_mode = "trust" if current == "active" else "active"
    set_mode = getattr(db, "set_parent_engagement_mode", None)
    if not callable(set_mode):
        await callback_query.answer("Не удалось обновить режим.", show_alert=True)
        return
    await set_mode(parent_id, new_mode)
    await render_profile_screen(callback_query.message, db, parent_id)
    await callback_query.answer(
        "Режим обновлён."
        if new_mode == "active"
        else "Режим обновлён."
    )


@router.callback_query(lambda c: c.data.startswith("parent:child:") and c.data.endswith(":schedule"))
async def process_parent_child_schedule(callback_query: types.CallbackQuery, db: Database):
    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    engagement_mode = _resolve_engagement_mode(user)
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    if child.get("link_status") != "linked":
        await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview, engagement_mode)
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
    if _resolve_engagement_mode(user) == "trust":
        await callback_query.answer(
            "Вы выбрали доверительный режим. Сменить можно в Ещё → Профиль.",
            show_alert=True,
        )
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

    _, user, _ = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    if _resolve_engagement_mode(user) == "trust":
        await callback_query.answer(
            "Вы выбрали доверительный режим. Сменить можно в Ещё → Профиль.",
            show_alert=True,
        )
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
    engagement_mode = _resolve_engagement_mode(user)
    if engagement_mode == "trust":
        await callback_query.answer(
            "Вы выбрали доверительный режим. Сменить можно в Ещё → Профиль.",
            show_alert=True,
        )
        return
    parts = callback_query.data.split(":")
    link_id = int(parts[2])
    status = parts[4]
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    if child.get("link_status") != "linked":
        await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview, engagement_mode)
        await callback_query.answer()
        return
    items = await _get_parent_child_homework(db, parent_id, link_id, status, preview)
    child_user_id = child.get("student_id")
    child_user = await db.get_user(child_user_id) if child_user_id else None
    child_exempt = bool(child_user.get("homework_exempt")) if child_user else False
    await _edit_text_for_actor(
        callback_query.message,
        build_homework_text(list(items or []), status, homework_exempt=child_exempt),
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
    engagement_mode = _resolve_engagement_mode(user)
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child:
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return
    if child.get("link_status") != "linked":
        await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview, engagement_mode)
        await callback_query.answer()
        return
    child_student_id = child.get("student_id")
    balance = int(child.get("lesson_balance") or 0)
    transactions = list(await db.get_student_transactions(child_student_id) or []) if child_student_id else []
    await _edit_text_for_actor(
        callback_query.message,
        build_payment_text(balance, [], transactions=transactions),
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
    if _resolve_engagement_mode(user) == "trust":
        await callback_query.answer(
            "Вы выбрали доверительный режим. Сменить можно в Ещё → Профиль.",
            show_alert=True,
        )
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
    if _resolve_engagement_mode(user) == "trust":
        await callback_query.answer(
            "Вы выбрали доверительный режим. Сменить можно в Ещё → Профиль.",
            show_alert=True,
        )
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


@router.callback_query(lambda c: c.data.startswith("parent:child:") and c.data.endswith(":progress"))
async def process_parent_child_progress(callback_query: types.CallbackQuery, db: Database):
    from utils.achievements import build_progress_text
    from utils.pulse_engine import _compute_streak_weeks

    parent_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "parent":
        await callback_query.answer("Этот экран доступен только родителям.", show_alert=True)
        return
    link_id = int(callback_query.data.split(":")[2])
    child = await _get_parent_child_link(db, parent_id, link_id, preview)
    if not child or child.get("link_status") != "linked":
        await callback_query.answer("Ребёнок не найден в вашем кабинете.", show_alert=True)
        return

    student_id = int(child["student_id"])
    progress = await db.get_student_progress(student_id)
    achievements = await db.get_student_achievements(student_id)

    first_lesson = progress.get("first_lesson_date")
    last_lesson = progress.get("last_lesson_date")
    total_lessons = int(progress.get("total_lessons") or 0)
    from datetime import datetime as _dt
    streak = _compute_streak_weeks(first_lesson, last_lesson, total_lessons, _dt.now())

    student = await db.get_user(student_id)
    pair = await db.get_pair_for_student(student_id) if hasattr(db, "get_pair_for_student") else None
    is_pair = bool(pair)
    pair_title = pair.get("title") if pair else None

    text = build_progress_text(
        progress, achievements, streak,
        is_pair=is_pair, pair_title=pair_title,
        speech_style=(student or {}).get("speech_style"),
    )
    await _edit_text_for_actor(
        callback_query.message, text,
        make_back_button_keyboard("◀️ К ребёнку", f"parent:child:{link_id}"),
        preview,
    )
    await callback_query.answer()


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
    engagement_mode = _resolve_engagement_mode(user)
    await _render_parent_child_home(callback_query.message, db, parent_id, link_id, preview, engagement_mode)
    await callback_query.answer()
