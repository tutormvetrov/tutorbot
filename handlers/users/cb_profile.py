"""Profile, contacts, materials, and danger zone callbacks."""
import logging

from aiogram import Router, types

from data.config import load_teacher_info
from handlers.users._cb_helpers import (
    _block_preview_action,
    _build_self_delete_warning,
    _edit_text_for_actor,
    _get_learning_student_id,
    _resolve_actor_context,
)
from keyboards.inline import (
    back_to_menu_keyboard,
    make_back_button_keyboard,
    make_contacts_keyboard,
    make_level_test_link_keyboard,
    make_materials_keyboard,
    make_profile_danger_keyboard,
    make_self_delete_confirm_keyboard,
    make_self_delete_review_keyboard,
)
from utils.db_api.postgresql import Database
from utils.ui_text import (
    build_action_result_text,
    build_contacts_text,
    build_materials_text,
    build_requisites_text,
    build_self_delete_final_warning_text,
    build_self_delete_success_text,
)

logger = logging.getLogger(__name__)

router = Router()


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
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    website_url = _get_project_site_url(info)
    resources: list = []
    if user and user.get("role") == "student":
        resource_owner_id = await _get_learning_student_id(db, user_id)
        list_resources = getattr(db, "list_student_resources", None)
        if callable(list_resources):
            try:
                resources = list(await list_resources(resource_owner_id) or [])
            except Exception:
                logger.warning("Failed to load student_resources", exc_info=True)
                resources = []
    else:
        list_global = getattr(db, "list_global_resources", None)
        if callable(list_global):
            try:
                resources = list(await list_global() or [])
            except Exception:
                resources = []
    await _edit_text_for_actor(
        callback_query.message,
        build_materials_text(resources, website_url=website_url),
        make_materials_keyboard(resources, website_url=website_url),
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('level_test:'))
async def process_level_test_choice(callback_query: types.CallbackQuery, db: Database):
    _, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Тест уровня доступен ученикам.", show_alert=True)
        return
    action = callback_query.data.split(':', 1)[1]
    url = _get_level_test_url()

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

    if user["role"] == "parent":
        get_parent_snapshot = getattr(db, "get_parent_deletion_snapshot", None)
        if callable(get_parent_snapshot):
            parent_snapshot = await get_parent_snapshot(user_id) or {}
        else:
            parent_snapshot = {}
        snapshot = {
            "role": "parent",
            "parent_links_as_parent": parent_snapshot.get("children_count", 0),
            "linked_children_count": parent_snapshot.get("linked_children_count", 0),
            "payments_as_payer": parent_snapshot.get("payments_as_payer", 0),
        }
    else:
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

    if user["role"] == "parent":
        delete_parent = getattr(db, "delete_parent_preserving_history", None)
        if callable(delete_parent):
            await delete_parent(callback_query.from_user.id)
        else:
            await db.delete_user_fully(callback_query.from_user.id)
    else:
        await db.delete_user_fully(callback_query.from_user.id)

    await callback_query.message.edit_text(
        build_self_delete_success_text(user["role"]),
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()


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
