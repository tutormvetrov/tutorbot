from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.inline import (
    back_to_menu_keyboard,
    parent_profile_keyboard,
    profile_keyboard,
    student_main_keyboard,
    make_parent_home_keyboard,
)
from utils.db_api.postgresql import Database
from utils.preview_mode import (
    apply_preview_to_payload,
    get_preview_context,
    get_preview_parent_children_overview,
    is_synthetic_parent_preview,
)
from utils.ui_text import (
    MAIN_MENU_TEXT,
    REGISTRATION_REQUIRED_TEXT,
    build_parent_home_text,
    build_profile_text,
    build_student_home_text,
    compute_student_cta,
)


async def _get_student_learning_context(db: Database, student_id: int) -> tuple[int, dict | None]:
    pair = None
    get_pair = getattr(db, "get_student_pair_for_student", None)
    if callable(get_pair):
        pair = await get_pair(student_id)
    if pair:
        return int(pair["primary_student_id"]), pair
    return student_id, None


async def get_user_home_payload(db: Database, actor_user_id: int) -> tuple[str, object]:
    preview = await get_preview_context(db, actor_user_id)
    effective_user_id = preview["target_id"] if preview else actor_user_id
    user = preview["user"] if preview else await db.get_user(effective_user_id)
    if not user:
        return apply_preview_to_payload(REGISTRATION_REQUIRED_TEXT, back_to_menu_keyboard, preview)

    if user.get("role") == "parent":
        if is_synthetic_parent_preview(preview):
            children = await get_preview_parent_children_overview(db, preview)
        else:
            children = list(await db.get_parent_children_overview(effective_user_id) or [])
        return apply_preview_to_payload(
            build_parent_home_text(user.get("full_name") or "—", children),
            make_parent_home_keyboard(children),
            preview,
        )

    if user.get("role") == "student":
        learning_user_id, pair = await _get_student_learning_context(db, effective_user_id)
        lessons = list(await db.get_active_lessons(learning_user_id) or [])
        next_lesson = lessons[0]["lesson_date"] if lessons and lessons[0].get("lesson_date") else None
        homework = list(await db.get_student_homework(learning_user_id, "active") or [])
        balance = await db.get_student_lesson_balance(learning_user_id)

        from datetime import datetime
        overdue_count = sum(
            1 for hw in homework
            if hw.get("deadline") and hw["deadline"] < datetime.now() and hw.get("status") == "active"
        )

        cta = compute_student_cta(user, balance, next_lesson, homework, overdue_count)

        journey_progress = None
        get_progress = getattr(db, "get_journey_progress", None)
        if callable(get_progress):
            try:
                journey_progress = await get_progress(effective_user_id)
            except Exception:
                journey_progress = None

        home_text = build_student_home_text(
            user,
            balance,
            active_homework_count=len(homework),
            next_lesson=next_lesson,
            pair=pair,
            journey_progress=journey_progress,
        )
        if cta:
            home_text = home_text + "\n\n" + cta["text"]

        rows: list[list[InlineKeyboardButton]] = []
        if cta:
            cta_url = cta.get("button_url")
            if cta_url:
                cta_btn = InlineKeyboardButton(text=cta["button_label"], url=cta_url)
            else:
                cta_btn = InlineKeyboardButton(
                    text=cta["button_label"],
                    callback_data=cta.get("button_callback", "back_to_menu"),
                )
            rows.append([cta_btn])
        if pair:
            rows.append([InlineKeyboardButton(text="🎯 Наша цель", callback_data="pair_goal:open")])
        if rows:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=rows + list(student_main_keyboard.inline_keyboard)
            )
        else:
            keyboard = student_main_keyboard

        return apply_preview_to_payload(home_text, keyboard, preview)

    return apply_preview_to_payload(MAIN_MENU_TEXT, student_main_keyboard, preview)


async def render_user_home(message: types.Message, db: Database, actor_user_id: int):
    text, keyboard = await get_user_home_payload(db, actor_user_id)
    await message.edit_text(text, reply_markup=keyboard)


async def get_profile_payload(db: Database, actor_user_id: int) -> tuple[str, object]:
    preview = await get_preview_context(db, actor_user_id)
    effective_user_id = preview["target_id"] if preview else actor_user_id
    user = preview["user"] if preview else await db.get_user(effective_user_id)
    if not user:
        return apply_preview_to_payload(REGISTRATION_REQUIRED_TEXT, back_to_menu_keyboard, preview)

    balance = 0
    next_lessons = []
    next_lesson = None
    pair = None
    if user["role"] == "student":
        learning_user_id, pair = await _get_student_learning_context(db, effective_user_id)
        balance = await db.get_student_lesson_balance(learning_user_id)
        next_lessons = await db.get_active_lessons(learning_user_id)
        next_lesson = next_lessons[0]["lesson_date"] if next_lessons and next_lessons[0].get("lesson_date") else None

    children = None
    if user["role"] == "parent":
        if is_synthetic_parent_preview(preview):
            children = await get_preview_parent_children_overview(db, preview)
        else:
            children = list(await db.get_parent_children_overview(effective_user_id) or [])

    text = build_profile_text(
        user,
        balance,
        next_lesson=next_lesson,
        reminders=user.get("lesson_reminders"),
        children=children,
        pair=pair,
    )
    if user["role"] == "student":
        keyboard = profile_keyboard
    elif user["role"] == "parent":
        keyboard = parent_profile_keyboard
    else:
        keyboard = back_to_menu_keyboard
    return apply_preview_to_payload(text, keyboard, preview)


async def render_profile_screen(message: types.Message, db: Database, actor_user_id: int):
    text, keyboard = await get_profile_payload(db, actor_user_id)
    await message.edit_text(text, reply_markup=keyboard)
