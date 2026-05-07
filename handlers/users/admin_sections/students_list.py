"""Обработчики каталога учеников (список, фильтры, сортировка, поиск)."""
from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import (
    MessageEditor,
    get_message_origin,
    is_admin,
    q,
)
from handlers.users.admin_sections._students_helpers import (
    _get_admin_students_view_state,
    _normalize_admin_students_filter,
    _normalize_admin_students_query,
    _normalize_admin_students_sort,
    _render_admin_students_page,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    make_back_button_keyboard,
)
from states.registration import AdminStudentsDirectory
from utils.db_api.postgresql import Database

router = Router()


@router.callback_query(lambda c: c.data == "admin:students")
async def admin_students(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter="all",
        admin_students_query="",
        admin_students_sort="name",
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:page:"))
async def admin_students_page(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    page = int(callback_query.data.split(":")[3])
    await _render_admin_students_page(callback_query.message, db, page=page, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:filter:"))
async def admin_students_filter(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filter_key = _normalize_admin_students_filter(callback_query.data.split(":")[3])
    _, query, sort_key = await _get_admin_students_view_state(state)
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query=query,
        admin_students_sort=sort_key,
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:sort:"))
async def admin_students_sort(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    sort_key = _normalize_admin_students_sort(callback_query.data.split(":")[3])
    filter_key, query, _ = await _get_admin_students_view_state(state)
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query=query,
        admin_students_sort=sort_key,
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:reset")
async def admin_students_reset(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter="all",
        admin_students_query="",
        admin_students_sort="name",
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:search_clear")
async def admin_students_search_clear(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filter_key, _, sort_key = await _get_admin_students_view_state(state)
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query="",
        admin_students_sort=sort_key,
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:search")
async def admin_students_search_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filter_key, query, sort_key = await _get_admin_students_view_state(state)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    hint_lines = []
    if query:
        hint_lines.extend([
            f"Текущий поиск: <b>{q(query)}</b>",
            "",
        ])

    await state.set_state(AdminStudentsDirectory.waiting_for_search)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query=query,
        admin_students_sort=sort_key,
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        "\n".join([
            "🔎 <b>Поиск ученика</b>",
            "",
            *hint_lines,
            "Введите имя, часть имени, язык, уровень или Telegram ID одним сообщением.",
        ]),
        reply_markup=make_back_button_keyboard("◀️ К списку учеников", "admin:students:search_back"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:search_back")
async def admin_students_search_back(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    page = int(data.get("admin_students_page") or 0)
    await state.set_state(AdminStudentsDirectory.browsing)
    await _render_admin_students_page(callback_query.message, db, page=page, state=state)
    await callback_query.answer()


@router.message(StateFilter(AdminStudentsDirectory.waiting_for_search))
async def admin_students_search_submit(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Поиск доступен только администратору.", reply_markup=back_to_admin_keyboard)
        return

    query = _normalize_admin_students_query(message.text)
    if not query:
        await message.answer(
            "⚠️ Введите имя или часть имени.",
            reply_markup=make_back_button_keyboard("◀️ К списку учеников", "admin:students:search_back"),
        )
        return

    data = await state.get_data()
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await state.update_data(admin_students_query=query, admin_students_page=0)
    await state.set_state(AdminStudentsDirectory.browsing)

    if origin_chat_id is None or origin_message_id is None:
        await message.answer("⚠️ Не удалось вернуть список. Откройте раздел «Ученики» заново.", reply_markup=back_to_admin_keyboard)
        return

    target = MessageEditor(message.bot, origin_chat_id, origin_message_id)
    await _render_admin_students_page(target, db, page=0, state=state)
