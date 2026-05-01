"""Admin handlers for managing per-student and global learning resources."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data import config
from keyboards.inline import (
    cancel_fsm_keyboard,
    make_admin_global_resources_keyboard,
    make_admin_resource_primary_choice_keyboard,
    make_admin_student_resources_keyboard,
    make_back_button_keyboard,
)
from states.registration import AdminAddResource
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_RESOURCE_INVALID_LABEL_TEXT,
    ADMIN_RESOURCE_INVALID_URL_TEXT,
    ADMIN_RESOURCE_PROMPT_LABEL_TEXT,
    ADMIN_RESOURCE_PROMPT_PRIMARY_TEXT,
    ADMIN_RESOURCE_PROMPT_URL_TEXT,
    build_admin_global_resources_text,
    build_admin_student_resources_text,
)

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


def _looks_like_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _render_student_resources(
    message: types.Message,
    db: Database,
    student_id: int,
    page: int,
):
    user = await db.get_user(student_id)
    name = user.get("full_name") if user else str(student_id)
    resources = list(await db.list_student_resources(student_id, include_global=False) or [])
    await message.edit_text(
        build_admin_student_resources_text(name, resources),
        reply_markup=make_admin_student_resources_keyboard(student_id, page, resources),
    )


async def _render_global_resources(message: types.Message, db: Database):
    resources = list(await db.list_global_resources() or [])
    await message.edit_text(
        build_admin_global_resources_text(resources),
        reply_markup=make_admin_global_resources_keyboard(resources),
    )


# ─── Entry points ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("admin:resources:student:"), StateFilter("*"))
async def open_student_resources(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    parts = callback_query.data.split(":")
    if len(parts) < 5:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    try:
        student_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    await _render_student_resources(callback_query.message, db, student_id, page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:resources:global", StateFilter("*"))
async def open_global_resources(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    await _render_global_resources(callback_query.message, db)
    await callback_query.answer()


# ─── Add resource flow ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("admin:resources:add:"))
async def start_add_resource(callback_query: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if len(parts) < 5:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    target = parts[3]  # telegram_id or "global"
    page_part = parts[4]
    student_id: int | None
    if target == "global":
        student_id = None
        page = 0
    else:
        try:
            student_id = int(target)
            page = int(page_part)
        except ValueError:
            await callback_query.answer("Некорректный маршрут.", show_alert=True)
            return

    await state.clear()
    await state.set_state(AdminAddResource.waiting_for_url)
    await state.update_data(
        resource_student_id=student_id,
        resource_origin_page=page,
    )
    await callback_query.message.edit_text(
        ADMIN_RESOURCE_PROMPT_URL_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddResource.waiting_for_url))
async def process_resource_url(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    url = (message.text or "").strip()
    if not _looks_like_url(url):
        await message.answer(ADMIN_RESOURCE_INVALID_URL_TEXT, reply_markup=cancel_fsm_keyboard)
        return
    await state.update_data(resource_url=url)
    await state.set_state(AdminAddResource.waiting_for_label)
    await message.answer(ADMIN_RESOURCE_PROMPT_LABEL_TEXT, reply_markup=cancel_fsm_keyboard)


@router.message(StateFilter(AdminAddResource.waiting_for_label))
async def process_resource_label(message: types.Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    label = (message.text or "").strip()
    if not label or len(label) > 60:
        await message.answer(ADMIN_RESOURCE_INVALID_LABEL_TEXT, reply_markup=cancel_fsm_keyboard)
        return
    data = await state.get_data()
    student_id = data.get("resource_student_id")
    page = int(data.get("resource_origin_page") or 0)
    url = data.get("resource_url") or ""

    new_id = await db.add_student_resource(
        student_id=student_id,
        label=label,
        url=url,
        is_primary=False,
        created_by=message.from_user.id,
    )
    await state.update_data(resource_new_id=new_id)
    await state.set_state(AdminAddResource.waiting_for_primary_choice)

    yes_cb = f"admin:resources:set_primary:{new_id}:{'global' if student_id is None else student_id}:{page}"
    no_cb = (
        "admin:resources:global"
        if student_id is None
        else f"admin:resources:student:{student_id}:{page}"
    )
    await message.answer(
        ADMIN_RESOURCE_PROMPT_PRIMARY_TEXT,
        reply_markup=make_admin_resource_primary_choice_keyboard(
            yes_callback=yes_cb,
            no_callback=no_cb,
        ),
    )


# ─── Set primary / delete ───────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("admin:resources:set_primary:"), StateFilter("*"))
async def set_resource_primary(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if len(parts) < 6:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    try:
        resource_id = int(parts[3])
    except ValueError:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    target = parts[4]
    try:
        page = int(parts[5])
    except ValueError:
        page = 0

    await state.clear()
    ok = await db.set_resource_primary(resource_id)
    if not ok:
        await callback_query.answer("Ссылка не найдена.", show_alert=True)
        return

    if target == "global":
        await _render_global_resources(callback_query.message, db)
    else:
        try:
            student_id = int(target)
        except ValueError:
            await callback_query.answer("Некорректный маршрут.", show_alert=True)
            return
        await _render_student_resources(callback_query.message, db, student_id, page)
    await callback_query.answer("⭐ Основная обновлена.")


@router.callback_query(lambda c: c.data and c.data.startswith("admin:resources:delete:"), StateFilter("*"))
async def delete_resource(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if len(parts) < 6:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    try:
        resource_id = int(parts[3])
    except ValueError:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    target = parts[4]
    try:
        page = int(parts[5])
    except ValueError:
        page = 0

    await state.clear()
    ok = await db.delete_student_resource(resource_id)
    if not ok:
        await callback_query.answer("Ссылка не найдена.", show_alert=True)
        return

    if target == "global":
        await _render_global_resources(callback_query.message, db)
    else:
        try:
            student_id = int(target)
        except ValueError:
            await callback_query.answer("Некорректный маршрут.", show_alert=True)
            return
        await _render_student_resources(callback_query.message, db, student_id, page)
    await callback_query.answer("🗑 Удалено.")
