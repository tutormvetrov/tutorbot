from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import is_admin
from keyboards.inline import (
    cancel_fsm_keyboard,
    make_back_button_keyboard,
    make_work_rule_edit_keyboard,
    make_work_rules_admin_keyboard,
    work_rules_broadcast_confirm_keyboard,
    work_rules_onboarding_keyboard,
)
from states.registration import AdminWorkRule
from utils.db_api.postgresql import Database
from utils.ui_text import build_admin_work_rules_text, build_onboarding_rules_text

router = Router()


async def _render_rules_list(message: types.Message, db: Database):
    rules = list(await db.get_work_rules() or [])
    text = build_admin_work_rules_text(rules)
    await message.edit_text(text, reply_markup=make_work_rules_admin_keyboard(rules))


@router.callback_query(lambda c: c.data == "admin:work_rules")
async def admin_work_rules(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_rules_list(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:work_rule:add")
async def admin_work_rule_add(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    await state.set_state(AdminWorkRule.waiting_for_title)
    await callback_query.message.edit_text(
        "📜 <b>Новое правило</b>\n\nВведите заголовок правила:",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminWorkRule.waiting_for_title))
async def admin_work_rule_title(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title or len(title) > 200:
        await message.answer("⚠️ Заголовок должен быть от 1 до 200 символов.", reply_markup=cancel_fsm_keyboard)
        return
    await state.update_data(rule_title=title)
    await state.set_state(AdminWorkRule.waiting_for_body)
    await message.answer(
        f"📜 Заголовок: <b>{title}</b>\n\nТеперь введите текст правила:",
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(AdminWorkRule.waiting_for_body))
async def admin_work_rule_body(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    body = (message.text or "").strip()
    if not body or len(body) > 2000:
        await message.answer("⚠️ Текст правила должен быть от 1 до 2000 символов.", reply_markup=cancel_fsm_keyboard)
        return
    data = await state.get_data()
    title = data["rule_title"]
    await db.add_work_rule(title, body)
    await state.clear()
    await message.answer(f"✅ Правило «{title}» добавлено.")
    rules = list(await db.get_work_rules() or [])
    text = build_admin_work_rules_text(rules)
    await message.answer(text, reply_markup=make_work_rules_admin_keyboard(rules))


@router.callback_query(lambda c: c.data and c.data.startswith("admin:work_rule:edit:"))
async def admin_work_rule_edit(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    rule_id = int(callback_query.data.split(":")[3])
    rule = await db.get_work_rule_by_id(rule_id)
    if not rule:
        await callback_query.answer("Правило не найдено.", show_alert=True)
        return
    from aiogram import html
    await callback_query.message.edit_text(
        f"📜 <b>{html.quote(rule['title'])}</b>\n\n{html.quote(rule['body'])}",
        reply_markup=make_work_rule_edit_keyboard(rule_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:work_rule:edit_title:"))
async def admin_work_rule_edit_title_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    rule_id = int(callback_query.data.split(":")[3])
    await state.clear()
    await state.update_data(edit_rule_id=rule_id)
    await state.set_state(AdminWorkRule.waiting_for_edit_title)
    await callback_query.message.edit_text(
        "✏️ Введите новый заголовок:",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminWorkRule.waiting_for_edit_title))
async def admin_work_rule_edit_title_done(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title or len(title) > 200:
        await message.answer("⚠️ Заголовок: 1-200 символов.", reply_markup=cancel_fsm_keyboard)
        return
    data = await state.get_data()
    await db.update_work_rule(data["edit_rule_id"], title=title)
    await state.clear()
    await message.answer("✅ Заголовок обновлён.")
    rules = list(await db.get_work_rules() or [])
    await message.answer(build_admin_work_rules_text(rules), reply_markup=make_work_rules_admin_keyboard(rules))


@router.callback_query(lambda c: c.data and c.data.startswith("admin:work_rule:edit_body:"))
async def admin_work_rule_edit_body_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    rule_id = int(callback_query.data.split(":")[3])
    await state.clear()
    await state.update_data(edit_rule_id=rule_id)
    await state.set_state(AdminWorkRule.waiting_for_edit_body)
    await callback_query.message.edit_text(
        "✏️ Введите новый текст правила:",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminWorkRule.waiting_for_edit_body))
async def admin_work_rule_edit_body_done(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    body = (message.text or "").strip()
    if not body or len(body) > 2000:
        await message.answer("⚠️ Текст: 1-2000 символов.", reply_markup=cancel_fsm_keyboard)
        return
    data = await state.get_data()
    await db.update_work_rule(data["edit_rule_id"], body=body)
    await state.clear()
    await message.answer("✅ Текст обновлён.")
    rules = list(await db.get_work_rules() or [])
    await message.answer(build_admin_work_rules_text(rules), reply_markup=make_work_rules_admin_keyboard(rules))


@router.callback_query(lambda c: c.data and c.data.startswith("admin:work_rule:delete:"))
async def admin_work_rule_delete(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    rule_id = int(callback_query.data.split(":")[3])
    await db.delete_work_rule(rule_id)
    await _render_rules_list(callback_query.message, db)
    await callback_query.answer("Правило удалено.")


# ── Rules broadcast ──────────────────────────────────────────────────────────


@router.callback_query(lambda c: c.data == "admin:work_rule:broadcast")
async def admin_work_rule_broadcast_start(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    students = await db.get_all_students()
    count = len(students) if students else 0
    if count == 0:
        await callback_query.answer("Нет активных учеников для рассылки.", show_alert=True)
        return
    rules = list(await db.get_work_rules() or [])
    text = build_onboarding_rules_text(rules)
    await callback_query.message.edit_text(
        f"📤 <b>Рассылка правил</b>\n\n"
        f"Получатели: <b>{count}</b> активных учеников.\n\n"
        f"Ученики получат дашборд с правилами и кнопку «Ознакомлен(а)».\n\n"
        f"<blockquote>{text}</blockquote>",
        reply_markup=work_rules_broadcast_confirm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:work_rule:broadcast:confirm")
async def admin_work_rule_broadcast_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    rules = list(await db.get_work_rules() or [])
    if not rules:
        await callback_query.answer("Нет правил для рассылки.", show_alert=True)
        return
    students = await db.get_all_students()
    if not students:
        await callback_query.answer("Нет активных учеников.", show_alert=True)
        return

    text = build_onboarding_rules_text(rules)
    sent, failed = 0, 0
    for student in students:
        try:
            await callback_query.bot.send_message(
                student["telegram_id"],
                text,
                reply_markup=work_rules_onboarding_keyboard,
            )
            sent += 1
        except Exception:
            failed += 1

    result_text = f"✅ <b>Рассылка завершена</b>\n\nОтправлено: {sent}"
    if failed:
        result_text += f"\nНе доставлено: {failed}"
    await callback_query.message.edit_text(
        result_text,
        reply_markup=make_back_button_keyboard("◀️ К правилам", "admin:work_rules"),
    )
    await callback_query.answer()
