"""Homework, lessons, notifications, progress, work rules, no-show callbacks."""
import logging

from aiogram import Router, html, types

from data import config
from handlers.users._cb_helpers import (
    _block_preview_action,
    _edit_text_for_actor,
    _get_learning_student_id,
    _resolve_actor_context,
    LESSON_PRESENCE_LABELS,
)
from handlers.users.cb_navigation import (
    _render_homework_list,
    _render_homework_detail,
    _render_notifications_screen,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    back_to_menu_keyboard,
    make_lesson_feedback_keyboard,
    make_no_show_confirm_keyboard,
    make_no_show_lessons_keyboard,
    make_write_to_student_keyboard,
    parent_more_keyboard,
    progress_back_keyboard,
    student_more_keyboard,
    work_rules_view_keyboard,
)
from utils.db_api.postgresql import Database
from utils.homework_text import homework_body_html
from utils.reschedule import decode_reschedule_slot, format_reschedule_slot_label
from utils.time import business_today
from utils.ui_text import (
    build_action_result_text,
    build_more_screen_text,
    build_no_show_confirm_text,
    build_no_show_notification_text,
    build_work_rules_text,
)

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data == 'homework')
async def process_homework(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Домашка доступна ученикам.", show_alert=True)
        return
    await _render_homework_list(callback_query.message, db, user_id, status="active", preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data in ('hw:active', 'hw:done'))
async def process_homework_list(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Домашка доступна ученикам.", show_alert=True)
        return
    status = callback_query.data.split(':')[1]
    await _render_homework_list(callback_query.message, db, user_id, status=status, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("hw:view:"))
async def process_homework_detail(callback_query: types.CallbackQuery, db: Database):
    parts = callback_query.data.split(":")
    if len(parts) != 4:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Домашка доступна ученикам.", show_alert=True)
        return
    hw_id = int(parts[2])
    status = parts[3]
    await _render_homework_detail(callback_query.message, db, user_id, hw_id, status, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("hw:file:"))
async def process_homework_attachment(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    get_user = getattr(db, "get_user", None)
    user = await get_user(callback_query.from_user.id) if callable(get_user) else None
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Домашка доступна ученикам.", show_alert=True)
        return

    parts = callback_query.data.split(":")
    if len(parts) != 4:
        await callback_query.answer("Некорректный маршрут.", show_alert=True)
        return

    hw_id = int(parts[2])
    status = parts[3]
    user_id = callback_query.from_user.id
    learning_user_id = await _get_learning_student_id(db, user_id)
    hw = await db.get_homework_by_id(hw_id)
    if not hw or hw["student_id"] != learning_user_id or (status and hw["status"] != status):
        await callback_query.answer("Задание не найдено или уже недоступно.", show_alert=True)
        return
    if not hw.get("attachment_file_id"):
        await callback_query.answer("У этого задания нет вложенного файла.", show_alert=True)
        return

    try:
        await callback_query.bot.send_document(user_id, hw["attachment_file_id"])
    except Exception:
        await callback_query.answer("Не удалось отправить файл. Попробуйте чуть позже.", show_alert=True)
        return

    await callback_query.answer("Файл отправлен.")


@router.callback_query(lambda c: c.data.startswith('hw_done:'))
async def process_homework_done(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    get_user = getattr(db, "get_user", None)
    user = await get_user(callback_query.from_user.id) if callable(get_user) else None
    user_role = (user or {}).get("role")
    if user_role and user_role != "student":
        await callback_query.answer("Отметка домашки доступна ученикам.", show_alert=True)
        return

    user_id = callback_query.from_user.id
    learning_user_id = await _get_learning_student_id(db, user_id)
    hw_id = int(callback_query.data.split(':')[1])
    hw = await db.get_homework_by_id(hw_id)
    if not hw or hw['student_id'] != learning_user_id or hw['status'] != 'active':
        await callback_query.message.edit_text(
            "ℹ️ Задание не найдено или уже отмечено как выполненное.",
            reply_markup=back_to_menu_keyboard,
        )
        await callback_query.answer()
        return

    await db.mark_homework_done(hw_id, learning_user_id)
    homework_html = homework_body_html(
        hw.get("title"),
        hw.get("description"),
        hw.get("attachment_name"),
        hw.get("attachment_mime_type"),
    ) or "—"

    student = await db.get_user(user_id)
    student_name = html.quote(student['full_name']) if student else str(user_id)
    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"✅ <b>ДЗ выполнено!</b>\n\n"
                f"👤 {student_name}\n"
                f"📝 Задание:\n{homework_html}",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу уведомление о выполненном ДЗ %s: %s", hw_id, exc)

    await _render_homework_list(callback_query.message, db, user_id, status="active")
    await callback_query.answer("Отметил как выполненное.")


@router.callback_query(lambda c: c.data.startswith('lesson_presence:'))
async def process_lesson_presence(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Доступно только ученикам.", show_alert=True)
        return

    parts = callback_query.data.split(':')
    if len(parts) != 3 or parts[1] not in LESSON_PRESENCE_LABELS:
        await callback_query.answer("Некорректный ответ.", show_alert=True)
        return

    status = parts[1]
    lesson_id = int(parts[2]) if parts[2].isdigit() else None
    if not lesson_id:
        await callback_query.answer("Урок не найден.", show_alert=True)
        return

    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow("SELECT * FROM lessons WHERE id = $1", lesson_id)
    if not lesson or lesson["student_id"] != callback_query.from_user.id:
        await callback_query.answer("Этот урок недоступен.", show_alert=True)
        return

    lesson_time = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else "дата уточняется"
    student_name = html.quote(user["full_name"] or callback_query.from_user.full_name or str(callback_query.from_user.id))
    answer_label = LESSON_PRESENCE_LABELS[status]

    await callback_query.message.edit_text(
        build_action_result_text(
            "Ответ принят",
            f"Статус по занятию: <b>{answer_label}</b>.",
            next_step="Спасибо за подтверждение.",
        ),
        reply_markup=back_to_menu_keyboard,
    )

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"📩 <b>Ответ по занятию</b>\n\n"
                f"👤 Ученик: {student_name}\n"
                f"📅 Урок: <b>{lesson_time}</b>\n"
                f"Статус: <b>{answer_label}</b>",
                reply_markup=make_write_to_student_keyboard(callback_query.from_user.id),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу статус по занятию %s: %s", lesson_id, exc)

    await callback_query.answer("Ответ отправлен.")


@router.callback_query(lambda c: c.data.startswith('reschedule_pick:'))
async def process_reschedule_pick(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    user = await db.get_user(callback_query.from_user.id)
    if not user or user["role"] != "student":
        await callback_query.answer("Доступно только ученикам.", show_alert=True)
        return

    token = callback_query.data.split(':', 1)[1]
    try:
        slot = decode_reschedule_slot(token)
    except ValueError:
        await callback_query.answer("Слот не распознан.", show_alert=True)
        return

    slot_label = format_reschedule_slot_label(slot)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Вариант переноса отправлен",
            f"Я передал преподавателю, что вам подходит <b>{html.quote(slot_label)}</b>.",
            next_step="Если нужно, можно ещё написать преподавателю вручную.",
        ),
        reply_markup=back_to_menu_keyboard,
    )

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                "🗓 <b>Выбран вариант переноса</b>\n\n"
                f"👤 Ученик: <b>{html.quote(user['full_name'])}</b>\n"
                f"📅 Предпочтительный слот: <b>{html.quote(slot_label)}</b>",
                reply_markup=make_write_to_student_keyboard(callback_query.from_user.id),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу выбранный слот переноса: %s", exc)

    await callback_query.answer("Вариант отправлен.")


@router.callback_query(lambda c: c.data == 'notif:manage')
async def process_notif_manage(callback_query: types.CallbackQuery, db: Database):
    user_id, _, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    await _render_notifications_screen(callback_query.message, db, user_id, preview=preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('notif:'))
async def process_notif_action(callback_query: types.CallbackQuery, db: Database):
    if await _block_preview_action(callback_query, db):
        return

    action = callback_query.data.split(':', 1)[1]
    user_id = callback_query.from_user.id

    from datetime import timedelta
    if action == 'disable':
        await db.set_lesson_reminders(user_id, 'disabled')
    elif action == 'pause_week':
        until = (business_today() + timedelta(weeks=1)).strftime('%d.%m.%Y')
        await db.set_lesson_reminders(user_id, f'paused_until:{until}')
    elif action == 'enable':
        await db.set_lesson_reminders(user_id, 'enabled')
    else:
        await callback_query.answer()
        return

    await _render_notifications_screen(callback_query.message, db, user_id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'more')
async def process_more(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") not in {"student", "parent"}:
        await callback_query.answer()
        return
    role = user["role"]
    keyboard = student_more_keyboard if role == "student" else parent_more_keyboard
    await _edit_text_for_actor(
        callback_query.message,
        build_more_screen_text(role),
        keyboard,
        preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'more:progress')
async def process_progress(callback_query: types.CallbackQuery, db: Database):
    from utils.achievements import build_progress_text
    from utils.pulse_engine import _compute_streak_weeks

    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    if not user or user.get("role") != "student":
        await callback_query.answer()
        return

    progress = await db.get_student_progress(user_id)
    achievements = await db.get_student_achievements(user_id)

    first_lesson = progress.get("first_lesson_date")
    last_lesson = progress.get("last_lesson_date")
    total_lessons = int(progress.get("total_lessons") or 0)
    from datetime import datetime
    streak = _compute_streak_weeks(first_lesson, last_lesson, total_lessons, datetime.now())

    pair = await db.get_pair_for_student(user_id) if hasattr(db, "get_pair_for_student") else None
    is_pair = bool(pair)
    pair_title = pair.get("title") if pair else None

    text = build_progress_text(
        progress, achievements, streak,
        is_pair=is_pair, pair_title=pair_title,
        speech_style=user.get("speech_style"),
    )
    await _edit_text_for_actor(
        callback_query.message, text, progress_back_keyboard, preview,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('lesson_feedback:') and not c.data.startswith('lesson_followup:'))
async def process_lesson_feedback(callback_query: types.CallbackQuery, db: Database):
    parts = callback_query.data.split(":")
    if len(parts) != 3:
        await callback_query.answer()
        return

    lesson_id = int(parts[1])
    rating = parts[2]
    if rating not in ("great", "ok", "hard"):
        await callback_query.answer()
        return

    user_id = callback_query.from_user.id
    user = await db.get_user(user_id)
    ss = (user.get("speech_style") or "informal") if user else "informal"

    already = await db.get_feedback_exists(lesson_id, user_id)
    if already:
        from utils.speech import choose_form
        msg = choose_form(ss, "Вы уже оценили этот урок!", "Ты уже оценил этот урок!")
        await callback_query.answer(msg, show_alert=False)
        return

    await db.save_lesson_feedback(lesson_id, user_id, rating)

    from utils.speech import choose_form
    response_texts = {
        "great": choose_form(ss, "Спасибо! Рад, что понравилось 🙂", "Спасибо! Рад, что понравилось 🙂"),
        "ok": "Принял, спасибо!",
        "hard": choose_form(
            ss,
            "Спасибо за честность — разберём на следующем занятии",
            "Спасибо за честность — разберём на следующем уроке",
        ),
    }
    await callback_query.answer(response_texts.get(rating, "Спасибо!"), show_alert=False)

    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(lambda c: c.data == 'work_rules')
async def process_work_rules(callback_query: types.CallbackQuery, db: Database):
    user_id, user, preview = await _resolve_actor_context(db, callback_query.from_user.id)
    rules = list(await db.get_work_rules() or [])
    text = build_work_rules_text(rules)
    await _edit_text_for_actor(callback_query.message, text, work_rules_view_keyboard, preview)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'work_rules:accept')
async def process_work_rules_accept(callback_query: types.CallbackQuery, db: Database):
    await db.set_rules_accepted(callback_query.from_user.id)
    await callback_query.message.edit_text(
        "✅ Отлично! Правила приняты. Добро пожаловать!",
        reply_markup=back_to_menu_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("lesson_followup:no_show:"))
async def lesson_followup_no_show(callback_query: types.CallbackQuery, db: Database):
    from handlers.users.admin_sections.common import is_admin
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    lesson_id = int(parts[2])
    student_id = int(parts[3])
    student = await db.get_user(student_id)
    student_name = student["full_name"] if student else str(student_id)
    lesson = await db.execute("SELECT * FROM lessons WHERE id = $1", lesson_id, fetchrow=True)
    if not lesson:
        await callback_query.answer("Урок не найден.", show_alert=True)
        return
    balance = await db.get_student_lesson_balance(student_id)
    text = build_no_show_confirm_text(lesson, student_name, balance)
    await callback_query.message.edit_text(
        text, reply_markup=make_no_show_confirm_keyboard(lesson_id, student_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:no_show:"))
async def admin_no_show_from_card(callback_query: types.CallbackQuery, db: Database):
    from handlers.users.admin_sections.common import is_admin
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    if parts[2] == "pick":
        lesson_id = int(parts[3])
        student_id = int(parts[4])
        student = await db.get_user(student_id)
        student_name = student["full_name"] if student else str(student_id)
        lesson = await db.execute("SELECT * FROM lessons WHERE id = $1", lesson_id, fetchrow=True)
        if not lesson:
            await callback_query.answer("Урок не найден.", show_alert=True)
            return
        balance = await db.get_student_lesson_balance(student_id)
        text = build_no_show_confirm_text(lesson, student_name, balance)
        await callback_query.message.edit_text(
            text, reply_markup=make_no_show_confirm_keyboard(lesson_id, student_id),
        )
    else:
        student_id = int(parts[2])
        page = int(parts[3])
        lessons = list(await db.get_active_lessons(student_id) or [])
        if not lessons:
            await callback_query.answer("Нет активных уроков.", show_alert=True)
            return
        await callback_query.message.edit_text(
            "⚠️ <b>Отметить прогул</b>\n\nВыберите урок:",
            reply_markup=make_no_show_lessons_keyboard(lessons, student_id, page),
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("no_show:confirm:"))
async def no_show_confirm(callback_query: types.CallbackQuery, db: Database):
    from handlers.users.admin_sections.common import is_admin
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    lesson_id = int(parts[2])
    student_id = int(parts[3])

    lesson = await db.execute("SELECT * FROM lessons WHERE id = $1", lesson_id, fetchrow=True)
    if not lesson or lesson.get("is_no_show"):
        await callback_query.answer("Урок уже обработан.", show_alert=True)
        return

    await db.mark_lesson_no_show(lesson_id, student_id)
    balance = await db.get_student_lesson_balance(student_id)

    await callback_query.message.edit_text(
        f"✅ Урок списан как прогул. Баланс: {balance}.",
        reply_markup=back_to_admin_keyboard,
    )

    notify_id = student_id
    parent = await db.get_active_parent_for_student(student_id)
    if parent:
        notify_id = parent["parent_id"]
    try:
        await callback_query.bot.send_message(
            notify_id,
            build_no_show_notification_text(lesson.get("lesson_date"), balance),
        )
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("no_show:cancel:"))
async def no_show_cancel(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "❌ Отменено.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()
