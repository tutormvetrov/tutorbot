"""Обработчики жизненного цикла ученика: деактивация, удаление, добавление."""
from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data.config import is_internal_test_account
from handlers.users.admin_sections.common import is_admin, q
from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_student_danger_confirm_keyboard,
    make_admin_student_danger_review_keyboard,
    make_back_button_keyboard,
    make_deactivate_confirm_keyboard,
    make_deactivate_review_keyboard,
    make_delete_confirm_keyboard,
    make_delete_review_keyboard,
    make_student_select_keyboard,
)
from states.registration import AdminAddStudent, AdminManageStudent
from utils.db_api.postgresql import Database
from utils.ui_text import build_action_result_text

router = Router()


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_prompt:"))
async def admin_student_deactivate_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    await callback_query.message.edit_text(
        f"🗑 <b>Деактивировать ученика {name}?</b>\n\n"
        "Ученик потеряет доступ к боту, но история занятий и оплат сохранится.",
        reply_markup=make_admin_student_danger_review_keyboard(
            f"admin:student_deactivate_review:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "⚠️ Перейти к подтверждению",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_review:"))
async def admin_student_deactivate_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Ученик <b>{name}</b> потеряет доступ к боту сразу после этого шага.",
            "История занятий и оплат сохранится.",
        ]),
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:student_deactivate_confirm:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "✅ Деактивировать ученика",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_confirm:"))
async def admin_student_deactivate_confirm_direct(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.deactivate_student(student_id)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Ученик деактивирован",
            f"Профиль <b>{name}</b> отключён, а история занятий и оплат сохранена.",
            next_step="При необходимости ученика можно снова добавить или зарегистрировать заново.",
        ),
        reply_markup=make_back_button_keyboard("◀️ К списку учеников", f"admin:students:page:{page}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_prompt:"))
async def admin_student_delete_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    snapshot = await db.get_user_deletion_snapshot(student_id)

    await callback_query.message.edit_text(
        f"💀 <b>Удалить ученика {name}?</b>\n\n"
        f"📚 Занятий: <b>{snapshot.get('lessons', 0)}</b>\n"
        f"💳 Платежей: <b>{snapshot.get('payments_as_student', 0)}</b>\n"
        f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>\n\n"
        "Это действие необратимо.",
        reply_markup=make_admin_student_danger_review_keyboard(
            f"admin:student_delete_review:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "⚠️ Перейти к подтверждению",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_review:"))
async def admin_student_delete_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Профиль <b>{name}</b> будет удалён вместе с уроками, оплатами и домашними заданиями.",
            "После этого восстановление из интерфейса невозможно.",
        ]),
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:student_delete_confirm:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "💀 Удалить навсегда",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_confirm:"))
async def admin_student_delete_confirm_direct(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.delete_user_fully(student_id)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Ученик удалён",
            f"Профиль <b>{name}</b> полностью удалён из базы.",
            next_step="Если человек снова запустит /start, он пройдёт регистрацию заново.",
        ),
        reply_markup=make_back_button_keyboard("◀️ К списку учеников", f"admin:students:page:{page}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("select_student:"), StateFilter(AdminManageStudent.waiting_for_student))
async def admin_select_student_manage(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    data = await state.get_data()
    action = data.get("action")
    await state.clear()

    if action == "delete":
        snapshot = await db.get_user_deletion_snapshot(student_id)
        await callback_query.message.edit_text(
            f"💀 <b>Удалить ученика {name}?</b>\n\n"
            "⚠️ Будут удалены все занятия, платежи и данные.\n"
            f"📚 Занятий: <b>{snapshot.get('lessons', 0)}</b>\n"
            f"💳 Платежей: <b>{snapshot.get('payments_as_student', 0)}</b>\n"
            f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>\n"
            f"🧭 Calendar-связей: <b>{snapshot.get('calendar_links', 0)}</b>\n\n"
            "После этого ученик сможет зарегистрироваться заново.",
            reply_markup=make_delete_review_keyboard(student_id),
        )
    else:
        await callback_query.message.edit_text(
            f"🗑 Деактивировать ученика <b>{name}</b>?\n\n"
            "Ученик не сможет пользоваться ботом. История платежей и занятий сохранится.",
            reply_markup=make_deactivate_review_keyboard(student_id),
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("deactivate_review:"))
async def admin_deactivate_student_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Ученик <b>{name}</b> потеряет доступ к боту сразу после этого шага.",
            "История платежей и занятий сохранится.",
        ]),
        reply_markup=make_deactivate_confirm_keyboard(student_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("deactivate_confirm:"))
async def admin_deactivate_student_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.deactivate_student(student_id)
    await callback_query.message.edit_text(
        f"✅ Ученик <b>{name}</b> деактивирован.\n\nИстория сохранена.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("delete_review:"))
async def admin_delete_student_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Профиль <b>{name}</b> будет удалён вместе с уроками, оплатами и домашними заданиями.",
            "После этого восстановление из интерфейса невозможно.",
        ]),
        reply_markup=make_delete_confirm_keyboard(student_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("delete_confirm:"))
async def admin_delete_student_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.delete_user_fully(student_id)
    await callback_query.message.edit_text(
        f"💀 Ученик <b>{name}</b> полностью удалён.\n\n"
        "При следующем /start он пройдёт регистрацию заново.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:add_student")
async def admin_add_student_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminAddStudent.waiting_for_name)
    await callback_query.message.edit_text(
        "👤 <b>Добавить ученика</b>\n\n"
        "Введите полное имя ученика (как оно написано в Google Calendar):\n\n"
        "Например: <code>Иван Петров</code>",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddStudent.waiting_for_name))
async def admin_add_student_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ Имя не может быть пустым.", reply_markup=cancel_fsm_keyboard)
        return
    await state.update_data(full_name=name)
    await state.set_state(AdminAddStudent.waiting_for_telegram_id)
    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\n"
        "Теперь введите Telegram ID ученика.\n\n"
        "Если ID неизвестен — введите <code>0</code>, тогда ученик сможет "
        "войти сам через /start и его данные обновятся автоматически.",
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(AdminAddStudent.waiting_for_telegram_id))
async def admin_add_student_id(message: types.Message, state: FSMContext, db: Database):
    try:
        telegram_id = int((message.text or "").strip())
        if telegram_id < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Введите числовой Telegram ID или <code>0</code> если неизвестен.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    full_name = data["full_name"]

    if telegram_id == 0:
        await message.answer(
            "⚠️ Добавление без Telegram ID пока не поддерживается.\n"
            "Попросите ученика написать боту /start — он зарегистрируется сам.",
            reply_markup=back_to_admin_keyboard,
        )
        await state.clear()
        return

    existing = await db.get_user(telegram_id)
    if existing:
        await state.clear()
        await message.answer(
            f"⚠️ Пользователь с ID <code>{telegram_id}</code> уже есть в базе:\n"
            f"<b>{q(existing['full_name'])}</b> ({q(existing['role'])})",
            reply_markup=back_to_admin_keyboard,
        )
        return

    if await db.is_telegram_id_blocked(telegram_id):
        await state.clear()
        await message.answer(
            f"🚫 ID <code>{telegram_id}</code> есть в списке блокировок.\n"
            "Сначала снимите блок командой <code>/unblock</code>, а потом добавляйте профиль.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    async with db.pool.acquire() as conn:
        internal = is_internal_test_account(full_name=full_name, telegram_id=telegram_id)
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, is_internal_account)
            VALUES ($1, $2, NULL, 'student', $3)
            """,
            telegram_id, full_name, internal,
        )

    await state.clear()
    internal_line = (
        "\n⚙️ Аккаунт помечен как внутренний тестовый и исключён из рабочей логики."
        if internal else ""
    )
    await message.answer(
        f"✅ <b>Ученик добавлен!</b>\n\n"
        f"👤 Имя: {q(full_name)}\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n\n"
        f"Теперь можно запустить /sync — занятия из Calendar привяжутся к этому ученику."
        f"{internal_line}",
        reply_markup=back_to_admin_keyboard,
    )
