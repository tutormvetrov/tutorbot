from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import (
    MessageEditor,
    get_message_origin,
    is_admin,
    parse_admin_callback,
    q,
)
from keyboards.inline import (
    _btn,
    back_to_admin_keyboard,
    make_admin_parent_card_keyboard,
    make_admin_parent_danger_keyboard,
    make_admin_parents_list_keyboard,
    make_admin_student_danger_confirm_keyboard,
    make_admin_student_danger_review_keyboard,
    make_back_button_keyboard,
)
from aiogram.types import InlineKeyboardMarkup
from states.registration import AdminParentsDirectory
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_PARENTS_EMPTY_TEXT,
    build_action_result_text,
    build_admin_parent_card_text,
    build_admin_parents_page_text,
)

router = Router()

ADMIN_PARENTS_PAGE_SIZE = 5


def _normalize_admin_parents_query(value: str | None) -> str:
    return " ".join((value or "").strip().split())


async def _get_admin_parents_view_state(state: FSMContext | None) -> str:
    if state is None:
        return ""
    data = await state.get_data()
    return _normalize_admin_parents_query(data.get("admin_parents_query"))


def _parent_matches_query(parent, query: str) -> bool:
    if not query:
        return True

    haystack = " ".join([
        str(parent.get("telegram_id") or ""),
        parent.get("full_name") or "",
    ]).lower()
    for token in query.lower().split():
        if token not in haystack:
            return False
    return True


def _filter_admin_parents(parents: list, query: str) -> list:
    return [
        parent
        for parent in parents
        if _parent_matches_query(parent, query)
    ]


def _parse_parent_page_callback(callback_data: str) -> tuple[int, int]:
    parts = callback_data.split(":")
    if len(parts) < 4:
        raise ValueError(f"Unsupported parent callback: {callback_data}")
    return int(parts[-2]), int(parts[-1])


async def _render_admin_parents_page(
    message: types.Message,
    db: Database,
    page: int = 0,
    state: FSMContext | None = None,
):
    parents = list(await db.get_parents_overview() or [])
    query = await _get_admin_parents_view_state(state)

    if not parents:
        if state is not None:
            await state.set_state(AdminParentsDirectory.browsing)
            await state.update_data(
                admin_parents_query="",
                admin_parents_page=0,
            )
        await message.edit_text(
            ADMIN_PARENTS_EMPTY_TEXT,
            reply_markup=make_back_button_keyboard("◀️ К разделу «Ученики»", "admin:cat:students"),
        )
        return

    filtered_parents = _filter_admin_parents(parents, query)
    total_pages = max(1, (len(filtered_parents) + ADMIN_PARENTS_PAGE_SIZE - 1) // ADMIN_PARENTS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    if state is not None:
        await state.set_state(AdminParentsDirectory.browsing)
        await state.update_data(
            admin_parents_query=query,
            admin_parents_page=page,
        )

    await message.edit_text(
        build_admin_parents_page_text(
            filtered_parents,
            page,
            ADMIN_PARENTS_PAGE_SIZE,
            query=query,
            total_count=len(parents),
        ),
        reply_markup=make_admin_parents_list_keyboard(
            filtered_parents,
            page=page,
            page_size=ADMIN_PARENTS_PAGE_SIZE,
            has_query=bool(query),
        ),
    )


async def _render_admin_parent_card(message: types.Message, db: Database, parent_id: int, page: int):
    parent = await db.get_user(parent_id)
    if not parent or parent.get("role") != "parent" or parent.get("is_active") is False:
        await message.edit_text(
            "⚠️ Родитель не найден или уже недоступен.",
            reply_markup=make_back_button_keyboard("◀️ К списку родителей", f"admin:parents:page:{page}"),
        )
        return

    children = list(await db.get_parent_children_overview(parent_id) or [])
    snapshot = await db.get_parent_deletion_snapshot(parent_id)
    await message.edit_text(
        build_admin_parent_card_text(parent, children, snapshot.get("payments_as_payer", 0)),
        reply_markup=make_admin_parent_card_keyboard(parent_id, page, children=children),
    )


async def _render_admin_parent_danger(message: types.Message, db: Database, parent_id: int, page: int):
    parent = await db.get_user(parent_id)
    if not parent or parent.get("role") != "parent" or parent.get("is_active") is False:
        await message.edit_text(
            "⚠️ Родитель не найден или уже недоступен.",
            reply_markup=make_back_button_keyboard("◀️ К списку родителей", f"admin:parents:page:{page}"),
        )
        return

    await message.edit_text(
        "\n".join([
            f"🛡 <b>Опасные действия: {q(parent['full_name'])}</b>",
            "",
            "Здесь можно отключить доступ родителя или удалить профиль.",
            "Удаление снимет связи с детьми, но не затронет историю оплат и учебный контур учеников.",
        ]),
        reply_markup=make_admin_parent_danger_keyboard(parent_id, page),
    )


@router.callback_query(lambda c: c.data == "admin:parents")
async def admin_parents(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminParentsDirectory.browsing)
    await state.update_data(
        admin_parents_query="",
        admin_parents_page=0,
    )
    await _render_admin_parents_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parents:page:"))
async def admin_parents_page(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    page = int(callback_query.data.split(":")[3])
    await _render_admin_parents_page(callback_query.message, db, page=page, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:parents:search")
async def admin_parents_search_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    query = await _get_admin_parents_view_state(state)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    hint_lines = []
    if query:
        hint_lines.extend([
            f"Текущий поиск: <b>{q(query)}</b>",
            "",
        ])

    await state.set_state(AdminParentsDirectory.waiting_for_search)
    await state.update_data(
        admin_parents_query=query,
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        "\n".join([
            "🔎 <b>Поиск родителя</b>",
            "",
            *hint_lines,
            "Введите имя, часть имени или Telegram ID одним сообщением.",
        ]),
        reply_markup=make_back_button_keyboard("◀️ К списку родителей", "admin:parents:search_back"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:parents:search_clear")
async def admin_parents_search_clear(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await state.set_state(AdminParentsDirectory.browsing)
    await state.update_data(
        admin_parents_query="",
        admin_parents_page=0,
    )
    await _render_admin_parents_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:parents:search_back")
async def admin_parents_search_back(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    page = int(data.get("admin_parents_page") or 0)
    await state.set_state(AdminParentsDirectory.browsing)
    await _render_admin_parents_page(callback_query.message, db, page=page, state=state)
    await callback_query.answer()


@router.message(StateFilter(AdminParentsDirectory.waiting_for_search))
async def admin_parents_search_submit(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer(
            "⚠️ Поиск доступен только администратору.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    query = _normalize_admin_parents_query(message.text)
    if not query:
        await message.answer(
            "⚠️ Введите имя или часть имени.",
            reply_markup=make_back_button_keyboard("◀️ К списку родителей", "admin:parents:search_back"),
        )
        return

    data = await state.get_data()
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await state.update_data(
        admin_parents_query=query,
        admin_parents_page=0,
    )
    await state.set_state(AdminParentsDirectory.browsing)

    if origin_chat_id is None or origin_message_id is None:
        await message.answer(
            "⚠️ Не удалось вернуть список. Откройте раздел «Родители» заново.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    target = MessageEditor(message.bot, origin_chat_id, origin_message_id)
    await _render_admin_parents_page(target, db, page=0, state=state)


@router.callback_query(lambda c: c.data.startswith("admin:parent_card:"))
async def admin_parent_card(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    await _render_admin_parent_card(callback_query.message, db, parent_id, page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_danger:"))
async def admin_parent_danger(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    await _render_admin_parent_danger(callback_query.message, db, parent_id, page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_deactivate_prompt:"))
async def admin_parent_deactivate_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    parent = await db.get_user(parent_id)
    if not parent or parent.get("role") != "parent" or parent.get("is_active") is False:
        await callback_query.answer("Родитель не найден.", show_alert=True)
        return
    snapshot = await db.get_parent_deletion_snapshot(parent_id)
    await callback_query.message.edit_text(
        "\n".join([
            f"🗑 <b>Деактивировать родителя {q(parent['full_name'])}?</b>",
            "",
            f"👧 Связей с детьми: <b>{snapshot.get('children_count', 0)}</b>",
            f"💳 Оплат как плательщик: <b>{snapshot.get('payments_as_payer', 0)}</b>",
            "",
            "Родитель потеряет доступ к боту. Связи и история сохранятся.",
        ]),
        reply_markup=make_admin_student_danger_review_keyboard(
            f"admin:parent_deactivate_review:{parent_id}:{page}",
            f"admin:parent_danger:{parent_id}:{page}",
            "⚠️ Перейти к подтверждению",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_deactivate_review:"))
async def admin_parent_deactivate_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    parent = await db.get_user(parent_id)
    name = q(parent["full_name"]) if parent else str(parent_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Родитель <b>{name}</b> сразу потеряет доступ к боту.",
            "Связи с детьми и история оплат останутся в базе.",
        ]),
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:parent_deactivate_confirm:{parent_id}:{page}",
            f"admin:parent_danger:{parent_id}:{page}",
            "✅ Деактивировать родителя",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_deactivate_confirm:"))
async def admin_parent_deactivate_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    parent = await db.get_user(parent_id)
    name = q(parent["full_name"]) if parent else str(parent_id)
    await db.deactivate_parent(parent_id)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Родитель деактивирован",
            f"Профиль <b>{name}</b> отключён. Связи с детьми и история оплат сохранены.",
            next_step="При необходимости профиль можно будет удалить позже отдельным действием.",
        ),
        reply_markup=make_back_button_keyboard("◀️ К списку родителей", f"admin:parents:page:{page}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_delete_prompt:"))
async def admin_parent_delete_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    parent = await db.get_user(parent_id)
    if not parent or parent.get("role") != "parent" or parent.get("is_active") is False:
        await callback_query.answer("Родитель не найден.", show_alert=True)
        return
    snapshot = await db.get_parent_deletion_snapshot(parent_id)
    await callback_query.message.edit_text(
        "\n".join([
            f"💀 <b>Удалить родителя {q(parent['full_name'])}?</b>",
            "",
            f"👧 Связей с детьми: <b>{snapshot.get('children_count', 0)}</b>",
            f"✅ Привязанных детей: <b>{snapshot.get('linked_children_count', 0)}</b>",
            f"💳 Оплат как плательщик: <b>{snapshot.get('payments_as_payer', 0)}</b>",
            "",
            "Профиль и связи с детьми будут удалены.",
            "История оплат и учебный контур учеников сохранятся.",
        ]),
        reply_markup=make_admin_student_danger_review_keyboard(
            f"admin:parent_delete_review:{parent_id}:{page}",
            f"admin:parent_danger:{parent_id}:{page}",
            "⚠️ Перейти к подтверждению",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_delete_review:"))
async def admin_parent_delete_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    parent = await db.get_user(parent_id)
    name = q(parent["full_name"]) if parent else str(parent_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Профиль <b>{name}</b> будет удалён из базы.",
            "Связи с детьми будут сняты, а payer_id в оплатах будет очищен.",
            "История учеников и их оплат останется на месте.",
        ]),
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:parent_delete_confirm:{parent_id}:{page}",
            f"admin:parent_danger:{parent_id}:{page}",
            "💀 Удалить родителя",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:parent_delete_confirm:"))
async def admin_parent_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parent_id, page = _parse_parent_page_callback(callback_query.data)
    parent = await db.get_user(parent_id)
    name = q(parent["full_name"]) if parent else str(parent_id)
    await db.delete_parent_preserving_history(parent_id)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Родитель удалён",
            f"Профиль <b>{name}</b> удалён. Связи сняты, история оплат и данные учеников сохранены.",
            next_step="Если этот человек снова запустит /start, он сможет зарегистрироваться заново.",
        ),
        reply_markup=make_back_button_keyboard("◀️ К списку родителей", f"admin:parents:page:{page}"),
    )
    await callback_query.answer()


# ─── Manual parent-student linking ───────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("admin:parent:link_student:"))
async def admin_parent_link_student(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 4)
    parent_id = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 else 0
    students = list(await db.get_students_without_parent() or [])
    if not students:
        await callback_query.answer("Нет учеников без привязки к родителю.", show_alert=True)
        return
    rows = []
    for s in students:
        rows.append([_btn(
            s["full_name"],
            f"admin:parent:pick_student:{parent_id}:{s['telegram_id']}:{page}",
        )])
    rows.append([_btn("◀️ Назад", f"admin:parent_card:{parent_id}:{page}")])
    await callback_query.message.edit_text(
        "➕ <b>Привязать ученика</b>\n\nВыберите ученика из списка:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:parent:pick_student:"))
async def admin_parent_pick_student(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 5)
    parent_id = int(parts[3])
    student_id = int(parts[4])
    page = int(parts[5]) if len(parts) > 5 else 0
    link_id = await db.create_parent_student_link(parent_id, student_id)
    if link_id is None:
        await callback_query.answer("Связь уже существует.", show_alert=True)
        await _render_admin_parent_card(callback_query.message, db, parent_id, page)
        return
    student = await db.get_user(student_id)
    student_name = q(student["full_name"]) if student else str(student_id)
    await callback_query.answer(f"✅ {student_name} привязан(а)")
    await _render_admin_parent_card(callback_query.message, db, parent_id, page)


@router.callback_query(lambda c: c.data and c.data.startswith("admin:parent:unlink:"))
async def admin_parent_unlink(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 5)
    link_id = int(parts[3])
    parent_id = int(parts[4])
    page = int(parts[5]) if len(parts) > 5 else 0
    link = await db.get_parent_student_link(link_id)
    if not link:
        await callback_query.answer("Связь не найдена.", show_alert=True)
        return
    student_name = q(link.get("student_name") or link.get("student_info") or "?")
    parent = await db.get_user(parent_id)
    parent_name = q(parent["full_name"]) if parent else str(parent_id)
    await callback_query.message.edit_text(
        f"⚠️ Отвязать <b>{student_name}</b> от <b>{parent_name}</b>?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                _btn("✅ Да, отвязать", f"admin:parent:unlink_confirm:{link_id}:{parent_id}:{page}"),
                _btn("❌ Отмена", f"admin:parent_card:{parent_id}:{page}"),
            ],
        ]),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:parent:unlink_confirm:"))
async def admin_parent_unlink_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 5)
    link_id = int(parts[3])
    parent_id = int(parts[4])
    page = int(parts[5]) if len(parts) > 5 else 0
    await db.deactivate_parent_student_link(link_id)
    await callback_query.answer("Связь снята.")
    await _render_admin_parent_card(callback_query.message, db, parent_id, page)
