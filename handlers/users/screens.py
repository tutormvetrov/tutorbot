from aiogram import types

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
)


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
        lessons = list(await db.get_active_lessons(effective_user_id) or [])
        next_lesson = lessons[0]["lesson_date"] if lessons and lessons[0].get("lesson_date") else None
        homework = list(await db.get_student_homework(effective_user_id, "active") or [])
        balance = await db.get_student_lesson_balance(effective_user_id)
        return apply_preview_to_payload(
            build_student_home_text(
                user,
                balance,
                active_homework_count=len(homework),
                next_lesson=next_lesson,
            ),
            student_main_keyboard,
            preview,
        )

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
    if user["role"] == "student":
        balance = await db.get_student_lesson_balance(effective_user_id)
        next_lessons = await db.get_active_lessons(effective_user_id)
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
