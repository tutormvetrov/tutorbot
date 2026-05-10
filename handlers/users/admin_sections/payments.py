from aiogram import types
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_context_keyboard,
    make_back_button_keyboard,
    make_payment_autoconfirm_keyboard,
    make_balance_writeoff_confirm_keyboard,
    make_payment_delete_confirm_keyboard,
    make_payment_delete_keyboard,
    make_pricing_rates_keyboard,
)
from states.registration import AdminAddPayment, AdminPricing
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_ADD_PAYMENT_AMOUNT_INVALID_TEXT,
    ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
    ADMIN_ADD_PAYMENT_COUNT_INVALID_TEXT,
    ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT,
    ADMIN_ADD_PAYMENT_START_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    build_admin_payments_text,
    build_payment_added_notification_text,
    build_pricing_rates_text,
)

from handlers.users.admin_sections.common import (
    get_message_origin,
    is_admin,
    parse_admin_callback,
    parse_admin_student_picker_callback_data,
    q,
    render_admin_student_picker,
    restore_admin_view,
)

router = Router()


def _parse_rate_line(text: str) -> tuple[str, int, int, float, str] | None:
    """Parse rate line: 'Название group_size duration amount [currency]'

    Examples:
        Инд_старый 1 90 2500
        Пара_120 2 120 4000 RUB
    """
    raw = (text or "").strip()
    if not raw:
        return None
    parts = raw.replace(",", ".").split()
    if len(parts) < 4:
        return None
    label = parts[0].replace("_", " ")
    try:
        group_size = int(parts[1])
        duration = int(parts[2])
        amount = float(parts[3])
    except ValueError:
        return None
    currency = parts[4].upper() if len(parts) > 4 else "RUB"
    if group_size <= 0 or duration <= 0 or amount <= 0:
        return None
    return label, group_size, duration, amount, currency


def _return_view_from_source(source: str | None) -> str:
    if source == "finance":
        return "admin:finance"
    if source == "education":
        return "admin:cat:education"
    return "admin:home"


def _reply_markup_for_return_view(return_view: str | None, student_id: int | None = None):
    if return_view:
        if return_view.startswith("admin:student_card:") and student_id is not None:
            parts = return_view.split(":")
            if len(parts) == 4:
                return make_admin_context_keyboard(student_id, int(parts[3]))
        return make_back_button_keyboard("◀️ Вернуться", return_view)
    return make_back_button_keyboard("◀️ Вернуться", return_view or "admin:home")


def _extract_rate_amount(rate_obj) -> float:
    """rate_obj может быть None, числом или asyncpg.Record/dict с полем amount."""
    if rate_obj is None:
        return 0.0
    if isinstance(rate_obj, (int, float)):
        return float(rate_obj)
    try:
        return float(rate_obj["amount"] or 0)
    except (KeyError, TypeError):
        return 0.0


def _student_return_view(student_id: int, page: int | None, source: str) -> str | None:
    if page is None:
        return None
    if source in {"actions", "settings", "danger"}:
        return f"admin:student_{source}:{student_id}:{page}"
    return f"admin:student_card:{student_id}:{page}"


async def _render_admin_payments(message: types.Message, db: Database, student_id: int, page: int | None = None, source: str = "card"):
    from datetime import date as _date
    student = await db.get_user(student_id)
    name = q(student['full_name']) if student else str(student_id)
    payments = await db.get_payments_for_student(student_id, limit=20)
    balance = await db.get_student_lesson_balance(student_id)
    carry_over_until = await db.get_carry_over_until(student_id)
    # Флаг считается активным, только если дата в будущем — иначе пора показать
    # «🔁 Перенести» снова, а не «↩️ Отменить».
    carry_active = carry_over_until if (carry_over_until and carry_over_until >= _date.today()) else None

    text = build_admin_payments_text(name, balance, payments)
    if carry_active:
        text += f"\n\n🔁 Защищён от авто-обнуления до {carry_active.strftime('%d.%m')}"

    await message.edit_text(
        text,
        reply_markup=make_payment_delete_keyboard(
            student_id, payments,
            page=page, source=source, balance=balance,
            carry_over_until=carry_active,
        ),
    )


async def _render_pricing_rates(message: types.Message, db: Database):
    rates = list(await db.get_pricing_rates() or [])
    try:
        await message.edit_text(
            build_pricing_rates_text(rates),
            reply_markup=make_pricing_rates_keyboard(rates),
        )
    except TelegramBadRequest as exc:
        # "message is not modified" — текст идентичен, ничего не делаем
        if "not modified" not in str(exc):
            raise


@router.callback_query(lambda c: c.data == "admin:pricing")
async def admin_pricing(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_pricing_rates(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:pricing:add")
async def admin_pricing_add_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    await state.set_state(AdminPricing.waiting_for_rate)
    await callback_query.message.edit_text(
        "💳 <b>Добавить или обновить тариф</b>\n\n"
        "Введите одной строкой:\n"
        "<code>Название кол_учеников длительность сумма [валюта]</code>\n\n"
        "Примеры:\n"
        "<code>Инд_старый 1 90 2500</code>\n"
        "<code>Пара_90 2 90 3500</code>\n"
        "<code>Инд_новый_120 1 120 3500 RUB</code>\n\n"
        "Название пишите без пробелов (вместо пробела _).\n"
        "Если тариф с таким названием уже есть, он будет обновлён.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminPricing.waiting_for_rate))
async def admin_pricing_rate_entered(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Настройка тарифов доступна только администратору.", reply_markup=back_to_admin_keyboard)
        return
    parsed = _parse_rate_line(message.text or "")
    if not parsed:
        await message.answer(
            "⚠️ Не понял формат. Пример: <code>Инд_старый 1 90 2500</code>",
            reply_markup=cancel_fsm_keyboard,
        )
        return
    label, group_size, duration, amount, currency = parsed
    await db.upsert_pricing_rate(group_size, duration, amount, currency, label=label)
    await state.clear()
    await message.answer(
        "✅ <b>Тариф сохранён</b>\n\n"
        f"Название: <b>{label}</b>\n"
        f"Формат: <b>{group_size} уч. · {duration} мин</b>\n"
        f"Цена за занятие: <b>{int(amount) if amount == int(amount) else amount} {currency}</b>",
        reply_markup=make_back_button_keyboard("◀️ К тарифам", "admin:pricing"),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:pricing:delete:"))
async def admin_pricing_delete(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    try:
        rate_id = int(parts[3])
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID.", show_alert=True)
        return
    await db.delete_pricing_rate(rate_id)
    await _render_pricing_rates(callback_query.message, db)
    await callback_query.answer("Тариф удалён.")


@router.callback_query(lambda c: c.data and c.data.startswith("lesson_followup:payment:"))
async def lesson_followup_payment(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(":")
    try:
        student_id = int(parts[2])
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID.", show_alert=True)
        return

    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        admin_return_view=f"admin:student_card:{student_id}:0",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddPayment.waiting_for_payment_amount)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:student_payments:'))
async def admin_student_payments(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"
    await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('payment_delete_confirm:'))
async def admin_payment_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    _, student_id_str, payment_id_str = parts[:3]
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"
    student_id = int(student_id_str)
    payment_id = int(payment_id_str)
    payment = await db.get_payment_by_id(payment_id)

    if not payment:
        await callback_query.message.edit_text(
            "⚠️ Оплата не найдена.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    date_str = payment['payment_date'].strftime('%d.%m.%Y') if payment.get('payment_date') else '—'
    await callback_query.message.edit_text(
        "🗑 <b>Удалить оплату?</b>\n\n"
        f"📅 Дата: <b>{date_str}</b>\n"
        f"💰 Сумма: <b>{int(payment['amount'])} ₽</b>\n"
        f"📚 Уроков: <b>{payment['lessons_count']}</b>\n"
        f"🎓 Остаток по платежу: <b>{payment['lessons_remaining']}</b>\n\n"
        "⚠️ Действие необратимо.",
        reply_markup=make_payment_delete_confirm_keyboard(student_id, payment_id, page=page, source=source),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('payment_delete:'))
async def admin_payment_delete(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    _, student_id_str, payment_id_str = parts[:3]
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"
    student_id = int(student_id_str)
    payment_id = int(payment_id_str)
    payment = await db.get_payment_by_id(payment_id)

    if not payment:
        await callback_query.message.edit_text(
            "⚠️ Оплата уже удалена.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await db.delete_payment(payment_id)
    await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
    await callback_query.answer("Оплата удалена.")


# ─── Balance write-off ───────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("admin:balance_writeoff_ask:"))
async def admin_balance_writeoff_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"

    balance = await db.get_student_lesson_balance(student_id)
    if balance == 0:
        await callback_query.answer("Баланс уже равен нулю.", show_alert=True)
        return

    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    if balance < 0:
        adjustment_label = f"+{abs(balance)}"
        note_kind = "Списание задолженности"
    else:
        adjustment_label = f"-{balance}"
        note_kind = "Обнуление положительного остатка"

    await callback_query.message.edit_text(
        f"🔄 <b>Обнулить баланс?</b>\n\n"
        f"👤 Ученик: {name}\n"
        f"📊 Текущий баланс: <b>{balance:+d}</b>\n"
        f"➡️ Будет добавлено: <b>{adjustment_label}</b>\n"
        f"📊 Баланс после: <b>0</b>\n\n"
        f"Будет создана запись «{note_kind}».",
        reply_markup=make_balance_writeoff_confirm_keyboard(student_id, page=page, source=source),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:balance_writeoff_do:"))
async def admin_balance_writeoff_execute(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"

    # Узнаём знак баланса до операции, чтобы корректно подписать транзакцию.
    pre_balance = await db.get_student_lesson_balance(student_id)
    if pre_balance == 0:
        await callback_query.answer("Баланс уже равен нулю.", show_alert=True)
        await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
        return
    note_kind = "Списание задолженности" if pre_balance < 0 else "Обнуление положительного остатка"

    amount = await db.reset_balance_to_zero(
        student_id=student_id,
        note=f"{note_kind} (admin {callback_query.from_user.id})",
    )
    if amount is None:
        await callback_query.answer("Баланс уже равен нулю.", show_alert=True)
        await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
        return

    await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
    await callback_query.answer(f"Баланс обнулён ({amount:+d}).")


# ─── Carry-over (перенос на следующую неделю) ────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("admin:carry_over_set:"))
async def admin_carry_over_set(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"

    until = await db.mark_carry_over(student_id)
    await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
    await callback_query.answer(
        f"🔁 Защищён от авто-обнуления до {until.strftime('%d.%m')}.",
        show_alert=False,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:carry_over_clear:"))
async def admin_carry_over_clear(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = parse_admin_callback(callback_query.data, 3)
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "card"

    await db.clear_carry_over(student_id)
    await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
    await callback_query.answer("Перенос отменён.")


@router.callback_query(lambda c: c.data.startswith('admin:add_payment'))
async def admin_add_payment_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_REGISTERED_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard
        )
        await callback_query.answer()
        return

    await state.clear()
    await state.update_data(
        admin_return_view=_return_view_from_source(source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddPayment.waiting_for_payment_student)
    await render_admin_student_picker(callback_query.message, db, flow="add_payment", page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:quick:add_payment:'))
async def admin_add_payment_quick(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    student_id_str = parts[3]
    page_str = parts[4]
    source = parts[5] if len(parts) > 5 else "card"
    student_id = int(student_id_str)
    page = int(page_str)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)

    await state.clear()
    await state.update_data(
        student_id=student_id,
        admin_return_view=_student_return_view(student_id, page, source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddPayment.waiting_for_payment_amount)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:') or c.data.startswith("admin:student_pick_select:add_payment:"),
    StateFilter(AdminAddPayment.waiting_for_payment_student),
)
async def admin_payment_student_selected(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data.startswith("admin:student_pick_select:"):
        _, student_id, _ = parse_admin_student_picker_callback_data(callback_query.data)
    else:
        student_id = int(callback_query.data.split(':')[1])
    await state.update_data(student_id=student_id)
    await state.set_state(AdminAddPayment.waiting_for_payment_amount)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_AMOUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddPayment.waiting_for_payment_amount))
async def admin_payment_amount_entered(message: types.Message, state: FSMContext, db: Database):
    try:
        amount = float((message.text or "").strip().replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            ADMIN_ADD_PAYMENT_AMOUNT_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await state.update_data(amount=amount)
    data = await state.get_data()
    student_id = data.get("student_id")

    pricing_ctx = await db.get_student_pricing_context(student_id) if student_id else None
    rate = _extract_rate_amount(pricing_ctx.get("rate") if pricing_ctx else None)

    if rate > 0 and amount % rate == 0:
        lessons = int(amount / rate)
        await message.answer(
            f"💰 {int(amount)} ₽ ÷ {int(rate)} ₽/урок = <b>{lessons} уроков</b>\n\nВерно?",
            reply_markup=make_payment_autoconfirm_keyboard(student_id, amount, lessons),
        )
        return

    await state.set_state(AdminAddPayment.waiting_for_payment_count)
    await message.answer(
        ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )


async def _finalize_payment(bot, db: Database, state: FSMContext, message, student_id: int, amount: float, count: int):
    await db.add_payment(student_id, amount, count)
    balance = await db.get_student_lesson_balance(student_id)

    student = await db.get_user(student_id)
    student_name = q(student['full_name']) if student else str(student_id)

    data = await state.get_data()
    return_view = data.get("admin_return_view")
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await state.clear()
    await restore_admin_view(bot, db, origin_chat_id, origin_message_id, return_view)
    await message.answer(
        f"✅ <b>Оплата добавлена</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"💰 Сумма: {int(amount)} ₽\n"
        f"🎓 Уроков: {count}\n\n"
        "Карточка и баланс уже обновлены.",
        reply_markup=_reply_markup_for_return_view(return_view, student_id),
    )

    notify_id = student_id
    parent = await db.get_active_parent_for_student(student_id)
    if parent:
        notify_id = parent["parent_id"]
    try:
        await bot.send_message(
            notify_id,
            build_payment_added_notification_text(amount, count, balance),
        )
    except Exception:
        pass


@router.message(StateFilter(AdminAddPayment.waiting_for_payment_count))
async def admin_payment_count_entered(message: types.Message, state: FSMContext, db: Database):
    try:
        count = int((message.text or "").strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            ADMIN_ADD_PAYMENT_COUNT_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    await _finalize_payment(message.bot, db, state, message, data['student_id'], data['amount'], count)


@router.callback_query(lambda c: c.data and c.data.startswith("payment_auto:confirm:"))
async def admin_payment_autoconfirm(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    amount = float(parts[3])
    count = int(parts[4])
    await _finalize_payment(callback_query.bot, db, state, callback_query.message, student_id, amount, count)
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("payment_auto:edit:"))
async def admin_payment_auto_edit(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    amount = float(parts[3])
    await state.update_data(student_id=student_id, amount=amount)
    await state.set_state(AdminAddPayment.waiting_for_payment_count)
    await callback_query.message.edit_text(
        ADMIN_ADD_PAYMENT_COUNT_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()
