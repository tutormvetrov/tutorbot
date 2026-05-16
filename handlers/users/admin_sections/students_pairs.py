"""Обработчики управления учебными парами."""
from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import is_admin, q
from handlers.users.admin_sections._students_helpers import (
    _render_admin_pair_card,
    _render_admin_pairs_page,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_pair_card_keyboard,
    make_admin_pair_primary_keyboard,
    make_back_button_keyboard,
)
from states.registration import AdminCreatePair, AdminEditPairName
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_NO_ACTIVE_STUDENTS_TEXT,
    build_action_result_text,
    build_admin_pair_card_text,
)

router = Router()


@router.callback_query(lambda c: c.data == "admin:pairs")
async def admin_pairs(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_pairs_page(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:pairs:add")
async def admin_pair_create_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    students = list(await db.get_all_students() or [])
    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_ACTIVE_STUDENTS_TEXT,
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await state.clear()
    await callback_query.message.edit_text(
        "\n".join([
            "👥 <b>Создать учебную пару</b>",
            "",
            "Сначала выберите основного контактного ученика.",
            "Через него будут идти общий баланс, расписание и домашние задания.",
        ]),
        reply_markup=make_admin_pair_primary_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:pairs:add_primary:"))
async def admin_pair_create_primary_selected(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    db: Database,
):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    primary_student_id = int(callback_query.data.split(":")[3])
    student = await db.get_user(primary_student_id)
    if not student or student.get("role") != "student" or student.get("is_active") is False:
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        pair_primary_student_id=primary_student_id,
        pair_primary_student_name=student["full_name"],
    )
    await state.set_state(AdminCreatePair.waiting_for_partner_name)
    await callback_query.message.edit_text(
        "\n".join([
            "👥 <b>Создать учебную пару</b>",
            "",
            f"Основной контакт: <b>{q(student['full_name'])}</b>",
            "",
            "Введите второго участника или всю пару.",
            "Можно: Полина, Безруковы Даниил и Полина, Даниил Безруков + Полина Смирнова.",
        ]),
        reply_markup=make_back_button_keyboard("◀️ К парам", "admin:pairs"),
    )
    await callback_query.answer()


@router.message(StateFilter(AdminCreatePair.waiting_for_partner_name))
async def admin_pair_create_partner_entered(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Создание пары доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    partner_name = (message.text or "").strip()
    if len(partner_name) < 2:
        await message.answer(
            "⚠️ Введите имя второго участника пары.",
            reply_markup=make_back_button_keyboard("◀️ К парам", "admin:pairs"),
        )
        return

    data = await state.get_data()
    primary_student_id = int(data["pair_primary_student_id"])
    primary_student_name = data["pair_primary_student_name"]
    create_pair = getattr(db, "create_student_pair", None)
    if not callable(create_pair):
        await state.clear()
        await message.answer("⚠️ В этой версии БД пары недоступны.", reply_markup=back_to_admin_keyboard)
        return

    pair_id = await create_pair(
        primary_student_id,
        primary_student_name,
        partner_name,
        onboarding_source="admin",
    )
    pair = await db.get_student_pair(pair_id)
    await state.clear()
    pair_title = q(pair.get("title") if pair else f"{primary_student_name} + {partner_name}")
    await message.answer(
        build_action_result_text(
            "Учебная пара создана",
            f"👥 <b>{pair_title}</b>\n"
            "Баланс, темп и домашние задания будут вестись общими через основной профиль.",
            next_step="Пара уже появилась в разделе «Пары».",
        ),
        reply_markup=make_admin_pair_card_keyboard(pair),
    )


@router.callback_query(lambda c: c.data.startswith("admin:pair_invite:"))
async def admin_pair_invite_link(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    pair_id = int(callback_query.data.split(":")[2])
    ensure_invite = getattr(db, "ensure_student_pair_invite", None)
    if not callable(ensure_invite):
        await callback_query.answer("В этой версии БД ссылки для пары недоступны.", show_alert=True)
        return

    invite = await ensure_invite(pair_id)
    if not invite:
        await callback_query.message.edit_text(
            "⚠️ Не нашёл второго участника в этой паре.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    payload = f"pair_{invite['invite_token']}"
    try:
        bot_me = await callback_query.bot.get_me()
        bot_username = getattr(bot_me, "username", None)
    except Exception:
        bot_username = None
    invite_entry = f"https://t.me/{bot_username}?start={payload}" if bot_username else f"/start {payload}"

    pair = await db.get_student_pair(pair_id)
    await callback_query.message.edit_text(
        "\n".join([
            "🔗 <b>Ссылка для второго участника</b>",
            "",
            f"Пара: <b>{q(invite['title'])}</b>",
            f"Кого подключаем: <b>{q(invite['member_name'])}</b>",
            "",
            f"<code>{invite_entry}</code>",
            "",
            "Отправьте эту ссылку второму участнику. После открытия бот привяжет его Telegram к паре, "
            "а баланс, расписание и ДЗ останутся общими через основной профиль.",
        ]),
        reply_markup=make_admin_pair_card_keyboard(pair) if pair else back_to_admin_keyboard,
    )
    await callback_query.answer("Ссылка готова.")


@router.callback_query(lambda c: c.data.startswith("admin:pair:"))
async def admin_pair_card(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    pair_id = int(callback_query.data.split(":")[2])
    await _render_admin_pair_card(callback_query.message, db, pair_id)
    await callback_query.answer()


def _pair_partner_name(pair: dict) -> str:
    primary = (pair.get("primary_student_name") or "").strip()
    for name in pair.get("member_names") or []:
        clean = str(name).strip()
        if clean and clean != primary:
            return clean
    return (pair.get("partner_names") or "").split(",")[0].strip()


@router.callback_query(lambda c: c.data.startswith("admin:pair_name:"), StateFilter("*"))
async def admin_pair_name_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if len(parts) != 4 or parts[2] not in {"primary", "partner", "common", "title"}:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    mode = parts[2]
    pair_id = int(parts[3])
    pair = await db.get_student_pair(pair_id)
    if not pair:
        await callback_query.answer("Пара не найдена.", show_alert=True)
        return
    labels = {
        "primary": ("ФИО основного участника", pair.get("primary_student_name") or ""),
        "partner": ("Имя второго участника", _pair_partner_name(pair)),
        "common": ("Общая фамилия", pair.get("common_surname") or "не задана"),
        "title": ("Название пары", pair.get("title") or ""),
    }
    title, current = labels[mode]
    await state.clear()
    await state.update_data(pair_name_id=pair_id, pair_name_mode=mode)
    await state.set_state(AdminEditPairName.waiting_for_text)
    await callback_query.message.edit_text(
        "\n".join([
            f"✏️ <b>{q(title)}</b>",
            "",
            f"Текущее: <b>{q(current)}</b>",
            "",
            "Пришлите новое значение одним сообщением.",
            "Для общей фамилии можно отправить «-», чтобы убрать её.",
        ]),
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminEditPairName.waiting_for_text))
async def admin_pair_name_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    pair_id = int(data.get("pair_name_id") or 0)
    mode = data.get("pair_name_mode")
    value = " ".join((message.text or "").split()).strip()
    if not pair_id or mode not in {"primary", "partner", "common", "title"}:
        await state.clear()
        return
    if not value:
        await message.answer("⚠️ Значение не может быть пустым.", reply_markup=cancel_fsm_keyboard)
        return
    pair = await db.get_student_pair(pair_id)
    if not pair:
        await state.clear()
        await message.answer("⚠️ Пара не найдена.", reply_markup=back_to_admin_keyboard)
        return
    if mode == "primary":
        await db.update_user_full_name(int(pair["primary_student_id"]), value)
        sync_parent_links = getattr(db, "sync_parent_links_for_student", None)
        if callable(sync_parent_links):
            await sync_parent_links(int(pair["primary_student_id"]), value)
    elif mode == "partner":
        await db.update_student_pair_partner_name(pair_id, value)
    elif mode == "common":
        await db.set_student_pair_common_surname(pair_id, None if value == "-" else value)
    else:
        await db.update_student_pair_title_manual(pair_id, value)
    await state.clear()
    updated = await db.get_student_pair(pair_id)
    await message.answer(
        build_action_result_text(
            "Пара обновлена",
            f"👥 <b>{q(updated.get('title') if updated else value)}</b>",
            next_step="Название пары обновлено в списках и карточках.",
        ),
        reply_markup=make_admin_pair_card_keyboard(updated or pair),
    )
