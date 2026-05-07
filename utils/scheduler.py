import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from data import config
from data.config import load_teacher_info
from keyboards.inline import (
    make_back_button_keyboard,
    make_first_lesson_invite_keyboard,
    make_lesson_feedback_keyboard,
    make_lesson_presence_keyboard,
    make_lesson_followup_keyboard,
    make_study_plan_open_keyboard,
    make_teacher_reply_keyboard,
)
from utils.brand import choose_tone_variant
from utils.homework_delivery import (
    send_batched_homework_notification,
    send_single_homework_notification,
)
from utils.homework_text import homework_body_html
from utils.nudge_engine import check_and_send_nudges
from utils.touch_engine import (
    parse_teacher_comment,
    render_touch_message,
    select_touch_type,
    should_send_touch,
)
from utils.observability import load_ops_status, update_job_status, update_ops_status, write_runtime_event
from utils.reschedule import encode_reschedule_slot, find_next_free_reschedule_slots, format_reschedule_slot_label
from utils.speech import choose_form
from utils.time import business_naive_now, business_today
from utils.ui_text import (
    build_feedback_after_first_message,
    build_finance_briefing_block,
    build_first_lesson_payment_invite_text,
    build_first_lesson_payment_invite_text_for_parent,
    build_goal_prompt_message,
    build_materials_intro_message,
    build_pair_weekly_report_text,
    build_parent_weekly_digest_text,
    build_prep_first_lesson_message,
    build_teacher_bookmark_reminder_text,
    build_teacher_lesson_followup_text,
    build_weekly_checkin_message,
    build_weekly_study_plan_text,
)

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database

logger = logging.getLogger(__name__)
LESSON_REMINDER_SEND_TIMEOUT_SECONDS = 20


def _get_online_lesson_links() -> tuple[str, str]:
    info = load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("vk_call", ""), contacts.get("google_meet", "")


async def build_reschedule_slot_payloads(db: "Database") -> list[tuple[str, str]]:
    slots = await find_next_free_reschedule_slots(db)
    return [(encode_reschedule_slot(slot), format_reschedule_slot_label(slot)) for slot in slots]


def _build_payment_reminder_text(stage: str, speech_style: str | None = None) -> str:
    prompt = choose_tone_variant(
        "Когда будет удобно, внесите",
        "Когда будет удобно, внесите",
        "Когда будет удобно, пожалуйста, внесите",
        "Когда будет удобно, пожалуйста, внесите",
    )
    evening_prompt = choose_tone_variant(
        "Постарайтесь",
        "Постарайтесь",
        "Пожалуйста, постарайтесь",
        "Буду признателен, если сможете",
    )
    if stage == "morning":
        return (
            "💰 <b>Напоминание об оплате</b>\n\n"
            "Доброе утро! Напоминаю, что занятия у нас оплачиваются на неделю вперёд.\n"
            f"Сейчас на {choose_form(speech_style, 'вашем', 'твоём')} балансе не осталось уроков.\n\n"
            f"{choose_form(speech_style, prompt, prompt.replace('внесите', 'внеси'))} оплату за ближайшую неделю.\n"
            "Реквизиты есть в меню: <b>💳 Реквизиты</b>."
        )

    return (
        "💰 <b>Оплата на новую неделю</b>\n\n"
        "Напоминаю, что для занятий на ближайшей неделе нужна предоплата.\n"
        "Сейчас уроков на балансе по-прежнему нет.\n\n"
        f"{choose_form(speech_style, evening_prompt, evening_prompt.replace('Постарайтесь', 'Постарайся').replace('сможете', 'сможешь'))} оплатить сегодня, чтобы расписание на неделю оставалось актуальным.\n"
        f"Если оплата уже отправлена или мы отдельно договорились, просто {choose_form(speech_style, 'проигнорируйте', 'проигнорируй')} это сообщение.\n\n"
        "Реквизиты: <b>💳 Реквизиты</b>."
    )


async def payment_reminder_job(bot, db: "Database", stage: str = "morning"):
    """Воскресные напоминания об оплате: мягкое утром и более серьёзное вечером."""
    students = await db.get_students_with_balances()
    if not students:
        return

    unpaid = []
    paid = []
    summary_title = (
        "📊 <b>Утренняя сводка по оплатам</b>\n"
        if stage == "morning" else
        "📊 <b>Вечерняя сводка по оплатам</b>\n"
    )

    for student in students:
        balance = student['lesson_balance']
        if balance == 0:
            unpaid.append((student['full_name'], balance))
            try:
                await bot.send_message(
                    student['telegram_id'],
                    _build_payment_reminder_text(stage, student.get("speech_style")),
                    reply_markup=make_teacher_reply_keyboard("payment"),
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание ученику {student['telegram_id']}: {e}")
        else:
            paid.append((student['full_name'], balance))

    # Сводка для преподавателя
    lines = [summary_title]
    if unpaid:
        lines.append(f"❌ <b>Не оплатили ({len(unpaid)}):</b>")
        for name, balance in unpaid:
            lines.append(f"  • {name} — {balance} ур.")
    if paid:
        lines.append(f"\n✅ <b>Оплатили ({len(paid)}):</b>")
        for name, balance in paid:
            lines.append(f"  • {name} — {balance} ур.")

    if config.ADMIN_ID:
        try:
            await bot.send_message(config.ADMIN_ID, "\n".join(lines))
        except Exception as e:
            logger.warning(f"Не удалось отправить сводку администратору: {e}")

    logger.info(
        "Напоминание об оплате (%s): %s не оплатили, %s оплатили.",
        stage,
        len(unpaid),
        len(paid),
    )
    update_job_status(
        f"payment_reminder_{stage}",
        "ok",
        unpaid=len(unpaid),
        paid=len(paid),
    )
    write_runtime_event("payment_reminder", "ok", stage=stage, unpaid=len(unpaid), paid=len(paid))


async def homework_reminder_job(bot, db: "Database"):
    """Ежедневно в 20:00 — напоминание о ДЗ с дедлайном завтра."""
    items = await db.get_homework_due_tomorrow()
    for hw in items:
        try:
            deadline_str = hw['deadline'].strftime('%d.%m.%Y') if hw['deadline'] else '—'
            homework_html = homework_body_html(
                hw.get('title'),
                hw.get('description'),
                hw.get('attachment_name'),
                hw.get('attachment_mime_type'),
            ) or "—"
            await bot.send_message(
                hw['telegram_id'],
                f"⏰ <b>Напоминание о домашнем задании!</b>\n\n"
                f"📝 Задание:\n{homework_html}\n"
                f"📅 Срок сдачи: <b>завтра, {deadline_str}</b>\n\n"
                f"{choose_form(hw.get('speech_style'), 'Не забудьте про это задание.', 'Не забудь про это задание.', 'Не забудь сделать, это важно 💪')}",
                reply_markup=make_teacher_reply_keyboard("homework", hw['id']),
            )
            await db.mark_homework_reminder_sent(hw['id'])
            logger.info(f"Напоминание ДЗ #{hw['id']} отправлено {hw['full_name']}")
        except Exception as e:
            logger.warning(f"Ошибка напоминания ДЗ #{hw['id']}: {e}")
    update_job_status("homework_reminder", "ok", sent=len(items))
    write_runtime_event("homework_reminder", "ok", sent=len(items))


async def queued_homework_delivery_job(bot, db: "Database"):
    now = business_naive_now()
    retry_before = now - timedelta(minutes=30)
    rows = [dict(row) for row in (await db.get_due_homework_deliveries(now, retry_before) or [])]
    due_items = len(rows)
    if not rows:
        update_job_status(
            "queued_homework_delivery",
            "ok",
            sent_students=0,
            sent_items=0,
            failed_items=0,
            due_items=0,
        )
        write_runtime_event(
            "queued_homework_delivery",
            "ok",
            sent_students=0,
            sent_items=0,
            failed_items=0,
            due_items=0,
        )
        return

    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["student_id"], []).append(row)

    sent_students = 0
    sent_items = 0
    failed_items = 0

    for student_id, items in grouped.items():
        try:
            if len(items) == 1:
                item = items[0]
                await send_single_homework_notification(
                    bot,
                    item,
                    item["delivery_kind"],
                    include_attachment=bool(item.get("include_attachment")),
                )
            else:
                await send_batched_homework_notification(bot, student_id, items)
            for item in items:
                await db.clear_homework_delivery(item["id"])
            sent_students += 1
            sent_items += len(items)
        except Exception as exc:
            logger.warning("Ошибка отложенной доставки ДЗ для ученика %s: %s", student_id, exc)
            for item in items:
                await db.mark_homework_delivery_failure(item["id"], now, str(exc))
            failed_items += len(items)

    status = "ok" if failed_items == 0 else "degraded"
    update_job_status(
        "queued_homework_delivery",
        status,
        sent_students=sent_students,
        sent_items=sent_items,
        failed_items=failed_items,
        due_items=due_items,
    )
    write_runtime_event(
        "queued_homework_delivery",
        status,
        sent_students=sent_students,
        sent_items=sent_items,
        failed_items=failed_items,
        due_items=due_items,
    )


async def homework_gap_check_job(bot, db: "Database"):
    """Проверяет, задано ли новое ДЗ между предыдущим и ближайшим уроком."""
    items = await db.get_lessons_missing_homework()
    sent_count = 0

    if not config.ADMIN_ID:
        update_job_status("homework_gap_check", "ok", sent=0, checked=len(items))
        write_runtime_event("homework_gap_check", "ok", sent=0, checked=len(items))
        return

    for lesson in items:
        previous_lesson = lesson.get("previous_lesson_date")
        previous_label = previous_lesson.strftime("%d.%m.%Y %H:%M") if previous_lesson else "—"
        next_label = lesson["lesson_date"].strftime("%d.%m.%Y %H:%M") if lesson.get("lesson_date") else "—"
        try:
            await bot.send_message(
                config.ADMIN_ID,
                "📚 <b>Проверьте домашнее задание</b>\n\n"
                f"👤 Ученик: <b>{lesson['full_name']}</b>\n"
                f"📅 Предыдущий урок: <b>{previous_label}</b>\n"
                f"⏭ Ближайший урок: <b>{next_label}</b>\n\n"
                "После предыдущего занятия пока не найдено новое ДЗ. Если оно уже выдано вне бота, это сообщение можно проигнорировать.",
            )
            await db.mark_homework_check_reminder_sent(lesson["id"])
            sent_count += 1
        except Exception as exc:
            logger.warning("Не удалось отправить напоминание по ДЗ для урока %s: %s", lesson["id"], exc)

    update_job_status("homework_gap_check", "ok", sent=sent_count, checked=len(items))
    write_runtime_event("homework_gap_check", "ok", sent=sent_count, checked=len(items))


async def lesson_reminder_job(bot, db: "Database"):
    """Напоминания о занятии: онлайн за ~10 минут, очно за ~1 час."""
    lessons = await db.get_lessons_for_reminder()
    sent_count = 0
    vk_call_url, google_meet_url = _get_online_lesson_links()
    for lesson in lessons:
        reminders = lesson.get('lesson_reminders') or 'enabled'
        # Проверяем паузу
        if reminders.startswith('paused_until:'):
            try:
                until_str = reminders.split(':', 1)[1]
                until_date = date.fromisoformat(
                    f"{until_str[6:10]}-{until_str[3:5]}-{until_str[0:2]}"
                )
                if business_today() <= until_date:
                    continue
                else:
                    await db.set_lesson_reminders(lesson['telegram_id'], 'enabled')
            except Exception:
                continue

        try:
            lesson_time = lesson['lesson_date'].strftime('%H:%M')
            is_offline = (lesson.get('lesson_format') or 'online') == 'offline'
            lead_text = "через час" if is_offline else "через 10 минут"
            message_text = (
                f"⏰ <b>Напоминание о занятии!</b>\n\n"
                f"Урок начнётся <b>{lead_text}</b> (сегодня в <b>{lesson_time}</b>).\n"
            )
            if is_offline:
                message_text += (
                    "\n📍 Формат: <b>очный урок</b>.\n"
                    f"{choose_form(lesson.get('speech_style'), 'Пожалуйста, подтвердите, что будете вовремя.', 'Подтверди, что будешь вовремя.', 'Подтверди, что будешь вовремя! 🚀')}\n\n"
                )
            else:
                message_text += (
                    "\n📍 Формат: <b>онлайн</b>.\n"
                    + (f"📞 VK-Звонок: {vk_call_url}\n" if vk_call_url else "")
                    + (f"📹 Google Meet (для тех, кто активно использует VPN): {google_meet_url}\n" if google_meet_url else "")
                    + "\n"
                )
            message_text += "Чтобы отключить напоминания: Профиль → 🔔 Управление уведомлениями"
            # Short timeout prevents one flaky Telegram request from blocking the
            # whole reminder loop and skipping the next cron windows.
            await asyncio.wait_for(
                bot.send_message(
                    lesson['telegram_id'],
                    message_text,
                    reply_markup=make_lesson_presence_keyboard(lesson['id']),
                ),
                timeout=LESSON_REMINDER_SEND_TIMEOUT_SECONDS,
            )
            await db.mark_lesson_reminder_sent(lesson['id'])
            sent_count += 1
            logger.info(f"Напоминание об уроке отправлено {lesson['full_name']}")
        except Exception as e:
            logger.warning(f"Ошибка напоминания об уроке {lesson['id']}: {e}")
    update_job_status("lesson_reminder", "ok", sent=sent_count, checked=len(lessons))
    write_runtime_event("lesson_reminder", "ok", sent=sent_count, checked=len(lessons))


async def teacher_lesson_followup_job(bot, db: "Database"):
    lessons = await db.get_lessons_for_teacher_followup()
    sent_count = 0

    if not config.ADMIN_ID:
        update_job_status("teacher_lesson_followup", "ok", sent=0, checked=len(lessons))
        write_runtime_event("teacher_lesson_followup", "ok", sent=0, checked=len(lessons))
        return

    for lesson in lessons:
        try:
            balance = await db.get_student_lesson_balance(lesson["student_id"])
            await asyncio.wait_for(
                bot.send_message(
                    config.ADMIN_ID,
                    build_teacher_lesson_followup_text(lesson),
                    reply_markup=make_lesson_followup_keyboard(lesson["id"], lesson["student_id"], balance=balance),
                ),
                timeout=LESSON_REMINDER_SEND_TIMEOUT_SECONDS,
            )
            await db.mark_teacher_followup_sent(lesson["id"])
            sent_count += 1
        except Exception as exc:
            logger.warning("Ошибка teacher follow-up для урока %s: %s", lesson["id"], exc)

    update_job_status("teacher_lesson_followup", "ok", sent=sent_count, checked=len(lessons))
    write_runtime_event("teacher_lesson_followup", "ok", sent=sent_count, checked=len(lessons))


async def teacher_bookmark_reminder_job(bot, db: "Database"):
    lessons = await db.get_lessons_for_teacher_bookmark_reminder()
    sent_count = 0

    if not config.ADMIN_ID:
        update_job_status("teacher_bookmark_reminder", "ok", sent=0, checked=len(lessons))
        write_runtime_event("teacher_bookmark_reminder", "ok", sent=0, checked=len(lessons))
        return

    for lesson in lessons:
        try:
            await asyncio.wait_for(
                bot.send_message(
                    config.ADMIN_ID,
                    build_teacher_bookmark_reminder_text(lesson),
                ),
                timeout=LESSON_REMINDER_SEND_TIMEOUT_SECONDS,
            )
            await db.mark_teacher_pre_lesson_note_sent(lesson["id"])
            sent_count += 1
        except Exception as exc:
            logger.warning("Ошибка teacher bookmark reminder для урока %s: %s", lesson["id"], exc)

    update_job_status("teacher_bookmark_reminder", "ok", sent=sent_count, checked=len(lessons))
    write_runtime_event("teacher_bookmark_reminder", "ok", sent=sent_count, checked=len(lessons))


async def first_lesson_payment_invite_job(bot, db: "Database"):
    """После первого урока, если ученик ещё не оплачивал, шлём
    спасибо + реквизиты + кнопку «Сообщить об оплате»."""
    students = await db.get_students_for_first_lesson_invite() or []
    sent_count = 0
    info = load_teacher_info()
    requisites = info.get("requisites", {})

    for student in students:
        try:
            pricing_context = await db.get_student_pricing_context(student["telegram_id"])
            parent = await db.get_active_parent_for_student(student["telegram_id"])
            if parent:
                text = build_first_lesson_payment_invite_text_for_parent(
                    parent.get("full_name") or "",
                    student.get("full_name") or "",
                    requisites,
                    pricing_context=pricing_context,
                    tariff_text=student.get("tariff_text"),
                )
                target_id = parent["telegram_id"]
            else:
                text = build_first_lesson_payment_invite_text(
                    student.get("full_name") or "",
                    requisites,
                    pricing_context=pricing_context,
                    speech_style=student.get("speech_style"),
                    tariff_text=student.get("tariff_text"),
                )
                target_id = student["telegram_id"]
            await asyncio.wait_for(
                bot.send_message(
                    target_id,
                    text,
                    reply_markup=make_first_lesson_invite_keyboard(),
                ),
                timeout=LESSON_REMINDER_SEND_TIMEOUT_SECONDS,
            )
            await db.mark_first_lesson_invite_sent(student["telegram_id"])
            sent_count += 1
            if parent:
                logger.info(
                    "Отправлено приглашение к оплате после первого урока родителю %s (%s) за ученика %s (%s)",
                    parent.get("full_name"),
                    parent["telegram_id"],
                    student.get("full_name"),
                    student["telegram_id"],
                )
            else:
                logger.info(
                    "Отправлено приглашение к оплате после первого урока ученику %s (%s)",
                    student.get("full_name"),
                    student["telegram_id"],
                )
        except Exception as exc:
            logger.warning(
                "Ошибка приглашения к оплате после первого урока для %s: %s",
                student.get("telegram_id"),
                exc,
            )

    update_job_status(
        "first_lesson_payment_invite",
        "ok",
        sent=sent_count,
        checked=len(students),
    )
    write_runtime_event(
        "first_lesson_payment_invite",
        "ok",
        sent=sent_count,
        checked=len(students),
    )


async def user_journey_dispatch_job(bot, db: "Database"):
    """Sends due onboarding nudges (goal prompt, materials intro, prep, feedback,
    weekly check-in) and re-schedules recurring weekly_checkin events."""
    from utils.brand import get_brand_tone
    from utils.db_api.journey import (
        JOURNEY_KIND_FEEDBACK_AFTER_FIRST,
        JOURNEY_KIND_GOAL_PROMPT,
        JOURNEY_KIND_MATERIALS_INTRO,
        JOURNEY_KIND_PREP_FIRST_LESSON,
        JOURNEY_KIND_WEEKLY_CHECKIN,
    )
    from keyboards.inline import _btn

    try:
        events = list(await db.get_due_journey_events(limit=50) or [])
    except Exception as exc:
        logger.warning("user_journey_dispatch_job: cannot read events: %s", exc)
        update_job_status("user_journey_dispatch", "error", error=str(exc))
        return

    if not events:
        update_job_status("user_journey_dispatch", "ok", sent=0, checked=0)
        return

    brand_tone = get_brand_tone()
    sent = 0
    for event in events:
        user_id = int(event["user_id"])
        kind = event["kind"]
        try:
            user = await db.get_user(user_id)
            if not user or not user.get("is_active", True):
                await db.dismiss_journey_event(int(event["id"]))
                continue

            text: str | None = None
            keyboard = None
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            if kind == JOURNEY_KIND_GOAL_PROMPT:
                if user.get("goal_text"):
                    await db.dismiss_journey_event(int(event["id"]))
                    continue
                text = build_goal_prompt_message(brand_tone)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [_btn("🎯 Указать цель", "goal:set")],
                    [_btn("🙅 Не сейчас", "goal:dismiss")],
                ])
            elif kind == JOURNEY_KIND_MATERIALS_INTRO:
                text = build_materials_intro_message(brand_tone)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [_btn("📁 Открыть материалы", "materials")],
                ])
            elif kind == JOURNEY_KIND_PREP_FIRST_LESSON:
                if user.get("role") != "student":
                    await db.dismiss_journey_event(int(event["id"]))
                    continue
                text = build_prep_first_lesson_message(brand_tone)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [_btn("📌 Учебный план", "study_plan")],
                ])
            elif kind == JOURNEY_KIND_FEEDBACK_AFTER_FIRST:
                if not user.get("first_lesson_invite_sent"):
                    # First lesson hasn't happened yet — dismiss and let the
                    # post-lesson hook re-create when appropriate.
                    await db.dismiss_journey_event(int(event["id"]))
                    continue
                text = build_feedback_after_first_message(brand_tone)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [_btn("✉️ Написать отзыв", "reply:lesson")],
                ])
            elif kind == JOURNEY_KIND_WEEKLY_CHECKIN:
                text = build_weekly_checkin_message(
                    brand_tone,
                    has_goal=bool(user.get("goal_text")),
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [_btn("✉️ Написать преподавателю", "reply:general")],
                ])
            else:
                await db.dismiss_journey_event(int(event["id"]))
                continue

            await asyncio.wait_for(
                bot.send_message(user_id, text, reply_markup=keyboard),
                timeout=LESSON_REMINDER_SEND_TIMEOUT_SECONDS,
            )
            await db.mark_journey_event_sent(int(event["id"]))
            sent += 1

            if kind == JOURNEY_KIND_WEEKLY_CHECKIN:
                await db.schedule_next_weekly_checkin(user_id, after=event["scheduled_at"])
            elif kind == JOURNEY_KIND_FEEDBACK_AFTER_FIRST:
                # Try to mark onboarding as completed if all 4 steps are done.
                progress = await db.get_journey_progress(user_id)
                if (
                    progress.get("level_test")
                    and progress.get("goal")
                    and progress.get("materials")
                    and progress.get("first_lesson")
                    and not progress.get("completed")
                ):
                    if await db.mark_onboarding_completed(user_id):
                        try:
                            await db.add_inbox_event("onboarding_completed", {
                                "telegram_id": user_id,
                                "full_name": user.get("full_name") or str(user_id),
                                "context": "onboarding",
                                "message_preview": "Прошёл все шаги онбординга.",
                            })
                        except Exception as exc:
                            logger.warning("inbox event onboarding_completed failed for %s: %s", user_id, exc)
        except Exception as exc:
            logger.warning(
                "user_journey_dispatch_job: failed to send %s to %s: %s",
                kind,
                user_id,
                exc,
            )

    update_job_status("user_journey_dispatch", "ok", sent=sent, checked=len(events))
    write_runtime_event("user_journey_dispatch", "ok", sent=sent, checked=len(events))


async def pair_weekly_report_job(bot, db: "Database"):
    """Monday morning weekly report for active pairs."""
    from utils.brand import get_brand_tone
    list_pairs = getattr(db, "list_active_pairs", None)
    if not callable(list_pairs):
        return
    pairs = list(await list_pairs() or [])
    if not pairs:
        update_job_status("pair_weekly_report", "ok", sent=0, checked=0)
        return
    brand_tone = get_brand_tone()
    sent = 0
    for pair in pairs:
        try:
            stats = await db.get_pair_progress(int(pair["id"]))
            if not stats:
                continue
            text = build_pair_weekly_report_text(stats, brand_tone)
            for telegram_id in stats.get("member_telegram_ids") or []:
                try:
                    await asyncio.wait_for(
                        bot.send_message(int(telegram_id), text),
                        timeout=LESSON_REMINDER_SEND_TIMEOUT_SECONDS,
                    )
                    sent += 1
                except Exception as exc:
                    logger.warning(
                        "pair_weekly_report_job: failed to send to %s: %s",
                        telegram_id,
                        exc,
                    )
        except Exception as exc:
            logger.warning("pair_weekly_report_job: failed pair %s: %s", pair.get("id"), exc)
    update_job_status("pair_weekly_report", "ok", sent=sent, checked=len(pairs))
    write_runtime_event("pair_weekly_report", "ok", sent=sent, checked=len(pairs))


async def calendar_sync_job(bot, db: "Database"):
    """Каждые 30 минут — автосинхронизация Google Calendar."""
    try:
        from utils.google_calendar import sync_calendar_to_db
        report = await sync_calendar_to_db(db)
        applied = report.get("imported", 0) + report.get("updated", 0)
        if applied or report.get("deleted", 0) or report.get("skipped", 0):
            logger.info(
                "Авто-синхронизация Google Calendar: imported=%s updated=%s skipped=%s deleted=%s.",
                report.get("imported", 0),
                report.get("updated", 0),
                report.get("skipped", 0),
                report.get("deleted", 0),
            )
        update_ops_status(
            status="running",
            scheduler="running",
            last_calendar_sync=report.get("synced_at"),
            calendar_imported=report.get("imported", 0),
            calendar_updated=report.get("updated", 0),
            calendar_skipped=report.get("skipped", 0),
            calendar_deleted=report.get("deleted", 0),
        )
        update_job_status(
            "calendar_sync",
            "ok",
            imported=report.get("imported", 0),
            updated=report.get("updated", 0),
            skipped=report.get("skipped", 0),
            deleted=report.get("deleted", 0),
        )
        write_runtime_event(
            "calendar_sync",
            "ok",
            imported=report.get("imported", 0),
            updated=report.get("updated", 0),
            skipped=report.get("skipped", 0),
            deleted=report.get("deleted", 0),
        )
    except Exception as e:
        logger.error(f"Ошибка авто-синхронизации Google Calendar: {e}")
        update_job_status("calendar_sync", "error", error=str(e))
        write_runtime_event("calendar_sync", "error", error=str(e))


async def lesson_completion_job(bot, db: "Database"):
    """Ежедневно в 00:30 МСК — завершает прошедшие уроки и списывает баланс."""
    lessons = await db.get_past_unprocessed_lessons()
    count = 0
    for lesson in lessons:
        try:
            await db.complete_lesson(lesson['id'], lesson['student_id'])
            count += 1
        except Exception as e:
            logger.warning(f"Ошибка завершения урока #{lesson['id']}: {e}")
    if count:
        logger.info(f"Авто-завершение: {count} уроков завершено, баланс списан.")
    update_job_status("lesson_completion", "ok", completed=count)
    write_runtime_event("lesson_completion", "ok", completed=count)


async def review_request_job(bot, db: "Database"):
    """Ежедневно проверяет, прошло ли 3 недели с первого занятия — отправляет просьбу об отзыве."""
    students = await db.get_students_for_review()
    sent_count = 0
    for student in students:
        try:
            await bot.send_message(
                student['telegram_id'],
                "⭐ <b>Оставьте отзыв о занятиях!</b>\n\n"
                "Прошло уже 3 недели с начала наших занятий.\n"
                f"Буду очень признателен, если {choose_form(student.get('speech_style'), 'Вы найдёте', 'ты найдёшь')} минутку и {choose_form(student.get('speech_style'), 'оставите', 'оставишь')} отзыв:\n\n"
                "👉 https://profi.ru/profile/VetrovMS2\n\n"
                + choose_tone_variant(
                    "Это помогает другим ученикам быстрее сориентироваться.",
                    "Это очень помогает другим ученикам найти хорошего преподавателя.",
                    "Это очень помогает другим ученикам найти хорошего преподавателя 🙏",
                    "Это помогает другим ученикам принять решение о занятиях.",
                ),
                reply_markup=make_teacher_reply_keyboard("review"),
            )
            await db.mark_review_sent(student['telegram_id'])
            sent_count += 1
            logger.info(f"Запрос отзыва отправлен: {student['full_name']} ({student['telegram_id']})")
        except Exception as e:
            logger.warning(f"Не удалось отправить запрос отзыва {student['telegram_id']}: {e}")
    update_job_status("review_request", "ok", sent=sent_count, checked=len(students))
    write_runtime_event("review_request", "ok", sent=sent_count, checked=len(students))


async def parent_weekly_digest_job(bot, db: "Database"):
    period_end = business_naive_now()
    period_start = period_end - timedelta(days=7)
    rows = await db.get_parent_weekly_digest_rows(period_start, period_end)
    if not rows:
        update_job_status("parent_weekly_digest", "ok", sent=0, checked=0)
        write_runtime_event("parent_weekly_digest", "ok", sent=0, checked=0)
        return

    grouped: dict[int, dict] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row["parent_id"],
            {
                "parent_name": row["parent_name"],
                "items": [],
            },
        )
        bucket["items"].append(
            {
                "student_name": row["student_name"],
                "had_lesson": row["had_lesson"],
                "active_homework_count": row["active_homework_count"],
                "lesson_balance": row["lesson_balance"],
                "next_lesson_date": row.get("next_lesson_date"),
            }
        )

    sent_count = 0
    for parent_id, payload in grouped.items():
        try:
            await bot.send_message(
                parent_id,
                build_parent_weekly_digest_text(payload["parent_name"], payload["items"]),
                reply_markup=make_back_button_keyboard("👨‍👩‍👧 Мои дети", "parent:home"),
            )
            sent_count += 1
        except Exception as exc:
            logger.warning("Не удалось отправить weekly digest родителю %s: %s", parent_id, exc)

    update_job_status("parent_weekly_digest", "ok", sent=sent_count, checked=len(grouped))
    write_runtime_event("parent_weekly_digest", "ok", sent=sent_count, checked=len(grouped))


async def study_plan_weekly_digest_job(bot, db: "Database"):
    student_rows = list(await db.get_learning_plan_weekly_student_rows() or [])
    parent_rows = list(await db.get_learning_plan_parent_digest_rows() or [])

    sent_students = 0
    for row in student_rows:
        recipients = await db.get_study_plan_recipients(row["student_id"])
        for recipient_id in recipients:
            try:
                await bot.send_message(
                    recipient_id,
                    build_weekly_study_plan_text(row),
                    reply_markup=make_study_plan_open_keyboard(),
                )
                sent_students += 1
            except Exception as exc:
                logger.warning("Не удалось отправить weekly study plan ученику %s: %s", recipient_id, exc)

    sent_parents = 0
    for row in parent_rows:
        try:
            await bot.send_message(
                row["parent_id"],
                build_weekly_study_plan_text(row, for_parent=True),
                reply_markup=make_study_plan_open_keyboard(parent_link_id=row["link_id"]),
            )
            sent_parents += 1
        except Exception as exc:
            logger.warning("Не удалось отправить weekly study plan родителю %s: %s", row["parent_id"], exc)

    update_job_status(
        "study_plan_weekly_digest",
        "ok",
        sent_students=sent_students,
        sent_parents=sent_parents,
        checked_students=len(student_rows),
        checked_parents=len(parent_rows),
    )
    write_runtime_event(
        "study_plan_weekly_digest",
        "ok",
        sent_students=sent_students,
        sent_parents=sent_parents,
        checked_students=len(student_rows),
        checked_parents=len(parent_rows),
    )


async def morning_briefing_job(bot, db: "Database"):
    """Утренняя сводка в 09:00: уроки на день + проблемы."""
    from keyboards.inline import make_briefing_keyboard
    from utils.pulse_engine import (
        build_briefing_text,
        compute_all_health,
        get_most_urgent_student_id,
        should_send_briefing,
    )

    # Check if pulse is enabled
    ops = load_ops_status()
    if not ops.get("pulse_enabled", True):
        update_job_status("morning_briefing", "ok", skipped_disabled=True)
        write_runtime_event("morning_briefing", "ok", skipped_disabled=True)
        return

    if not config.ADMIN_ID:
        return

    now = business_naive_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    health_list = await compute_all_health(db, now=now)
    today_lessons = await db.get_today_lessons_for_briefing(today_start, tomorrow_start)

    if not should_send_briefing(health_list, today_lessons or []):
        update_job_status("morning_briefing", "ok", skipped_no_content=True)
        write_runtime_event("morning_briefing", "ok", skipped_no_content=True)
        return

    text = build_briefing_text(health_list, today_lessons or [], today_date=now.date())

    try:
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        income_week = await db.get_income_period(week_start)
        discipline = list(await db.get_payment_discipline() or [])
        overdue_names = [
            d["full_name"] for d in discipline
            if d["balance"] <= 0 and d.get("last_payment_at")
        ]
        finance_block = build_finance_briefing_block(income_week, overdue_names)
        text = text + "\n\n" + finance_block
    except Exception:
        pass

    most_urgent = get_most_urgent_student_id(health_list)
    keyboard = make_briefing_keyboard(most_urgent)

    try:
        await bot.send_message(config.ADMIN_ID, text, reply_markup=keyboard)
    except Exception as exc:
        logger.warning("Не удалось отправить утреннюю сводку: %s", exc)

    update_job_status("morning_briefing", "ok", sent=1, problems=sum(1 for h in health_list if h["color"] != "green"))
    write_runtime_event("morning_briefing", "ok", sent=1)


async def homework_nudge_job(bot, db: "Database"):
    """ДЗ-надзиратель: 3-ступенчатая эскалация при невыдаче ДЗ после урока."""
    await check_and_send_nudges(bot, db)


async def between_lesson_touches_job(bot, db: "Database"):
    """Межурочные касания: персонализированные сообщения ученикам между уроками."""
    from utils.brand import get_brand_tone
    from utils.observability import load_touches_runtime
    from utils.pulse_engine import is_quiet_hours

    now = datetime.now()
    today = now.date()

    runtime_state = load_touches_runtime()
    if runtime_state.get("paused"):
        update_job_status("between_lesson_touches", "ok", paused=True, sent=0)
        write_runtime_event("between_lesson_touches", "ok", paused=True, sent=0)
        return

    if is_quiet_hours(now, for_student=True):
        update_job_status("between_lesson_touches", "ok", skipped_quiet=True, sent=0)
        write_runtime_event("between_lesson_touches", "ok", skipped_quiet=True, sent=0)
        return

    candidates = await db.get_touch_candidates()
    sent_count = 0
    checked = len(candidates) if candidates else 0

    brand_tone = get_brand_tone()

    for student in (candidates or []):
        student_id = student["telegram_id"]
        full_name = student.get("full_name") or "---"
        preferred_name = student.get("preferred_name")
        speech_style = student.get("speech_style")
        last_lesson = student.get("last_lesson_date")
        next_lesson = student.get("next_lesson_date")
        teacher_comment = student.get("teacher_comment")
        has_active_hw = bool(student.get("has_active_hw"))
        is_pair = bool(student.get("is_pair"))
        partner_name = student.get("partner_name")
        goal_text = student.get("goal_text")

        # Pull the past-week touch history once; pass it to should_send_touch
        # so day-cap, weekly-cap, and per-template-type cooldown all share data.
        week_ago = now - timedelta(days=7)
        recent = await db.get_recent_touches(student_id, since=week_ago) or []

        balance_row = await db.get_student_lesson_balance(student_id)
        balance = int(balance_row) if balance_row else 0

        # Coarse gate: per-day, weekly, lesson-day rules (no template type yet).
        if not should_send_touch(last_lesson, next_lesson, recent, today, balance):
            continue

        # Parse teacher comment and select touch type
        comment_data = parse_teacher_comment(teacher_comment)

        # Compute streak for motivation
        from utils.pulse_engine import compute_student_health
        health_data = await db.get_all_pulse_data()
        streak_weeks = 0
        for row in (health_data or []):
            if row.get("telegram_id") == student_id:
                h = compute_student_health(row, now=now)
                streak_weeks = h.get("streak_weeks", 0)
                break

        # Total lessons and goal reminder timing
        total_lessons = 0
        for row in (health_data or []):
            if row.get("telegram_id") == student_id:
                total_lessons = int(row.get("total_lessons") or 0)
                break

        last_goal_reminder_days = None
        if goal_text and recent:
            for t in recent:
                if t.get("template_type") == "goal_reminder":
                    last_goal_reminder_days = (now - t["sent_at"]).days
                    break

        touch_type = select_touch_type(
            comment_data, has_active_hw, streak_weeks, balance,
            total_lessons=total_lessons,
            goal_text=goal_text,
            last_goal_reminder_days=last_goal_reminder_days,
        )
        if not touch_type:
            continue

        # Re-check with the chosen template type to enforce per-type cooldown.
        if not should_send_touch(
            last_lesson, next_lesson, recent, today, balance,
            candidate_template_type=touch_type,
        ):
            continue

        # Find last template index for dedup
        last_template_index = None
        if recent:
            for t in recent:
                if t.get("template_type") == touch_type and t.get("template_index") is not None:
                    last_template_index = t["template_index"]
                    break

        from utils.achievements import compute_next_milestone
        next_milestone_text = compute_next_milestone(total_lessons) or ""

        context = {
            "topic": comment_data.get("topic") or comment_data.get("difficulty"),
            "difficulty": comment_data.get("difficulty"),
            "raw_first_sentence": comment_data.get("raw_first_sentence"),
            "N": streak_weeks,
            "total_lessons": total_lessons,
            "goal": goal_text or "",
            "next_milestone_text": next_milestone_text,
        }

        display_name = preferred_name or (
            full_name.split()[0] if full_name and full_name != "---" else full_name
        )

        message, tpl_idx = render_touch_message(
            template_type=touch_type,
            student_name=display_name,
            context=context,
            brand_tone=brand_tone,
            speech_style=speech_style,
            is_pair=is_pair,
            partner_name=partner_name,
            last_template_index=last_template_index,
        )
        if not message:
            continue

        try:
            await bot.send_message(student_id, message)
            await db.log_touch(
                student_id=student_id,
                template_type=touch_type,
                template_key=None,
                context_source="teacher_comment" if teacher_comment else ("homework" if has_active_hw else "goal"),
                context_snippet=(teacher_comment or "")[:100] if teacher_comment else None,
                template_index=tpl_idx,
            )
            sent_count += 1
        except Exception as exc:
            logger.warning("Не удалось отправить касание для %s: %s", full_name, exc)

    update_job_status("between_lesson_touches", "ok", checked=checked, sent=sent_count)
    write_runtime_event("between_lesson_touches", "ok", checked=checked, sent=sent_count)


async def achievement_check_job(bot, db: "Database"):
    """Daily job: check all students for new achievements, insert with notified=False."""
    from utils.achievements import ACHIEVEMENTS
    from utils.pulse_engine import _compute_streak_weeks

    students = await db.get_all_pulse_data()
    granted = 0

    for row in (students or []):
        student_id = row["telegram_id"]
        total_lessons = int(row.get("total_lessons") or 0)
        first_lesson = row.get("first_lesson_date")
        last_lesson = row.get("last_lesson_date")
        now = datetime.now()

        streak = _compute_streak_weeks(first_lesson, last_lesson, total_lessons, now)
        tenure_weeks = max(0, (now - first_lesson).days // 7) if first_lesson else 0
        goal_text = row.get("goal_text")

        progress = await db.get_student_progress(student_id)
        plan_total = int(progress.get("plan_total") or 0)
        plan_done = int(progress.get("plan_done") or 0)

        hw_months = await db.get_student_hw_perfect_months(student_id)

        metrics = {
            "total_lessons": total_lessons,
            "streak_weeks": streak,
            "tenure_weeks": tenure_weeks,
            "goal_text": goal_text,
            "plan_total": plan_total,
            "plan_done": plan_done,
            "hw_perfect_months": len(hw_months) if hw_months else 0,
        }

        for achievement in ACHIEVEMENTS:
            if achievement["check"](metrics):
                was_new = await db.grant_achievement(student_id, achievement["key"])
                if was_new:
                    granted += 1

    update_job_status("achievement_check", "ok", granted=granted, checked=len(students or []))
    write_runtime_event("achievement_check", "ok", granted=granted, checked=len(students or []))


async def achievement_notify_job(bot, db: "Database"):
    """Daily job: send congratulation messages for unnotified achievements."""
    from utils.achievements import build_achievement_congrats

    rows = await db.get_unnotified_achievements()
    sent = 0

    for row in (rows or []):
        try:
            text = build_achievement_congrats(
                row["achievement_key"],
                speech_style=row.get("speech_style"),
            )
            if not text:
                await db.mark_achievement_notified(row["id"])
                continue
            await asyncio.wait_for(
                bot.send_message(row["user_id"], text),
                timeout=10,
            )
            await db.mark_achievement_notified(row["id"])
            sent += 1
        except Exception as exc:
            logger.warning("Ошибка отправки достижения %s для %s: %s", row["achievement_key"], row["user_id"], exc)

    update_job_status("achievement_notify", "ok", sent=sent, total=len(rows or []))
    write_runtime_event("achievement_notify", "ok", sent=sent, total=len(rows or []))


async def lesson_feedback_request_job(bot, db: "Database"):
    """Send 'How was the lesson?' messages to students after lessons end."""
    lessons = await db.get_lessons_for_feedback_request()
    sent = 0

    for lesson in (lessons or []):
        try:
            ss = lesson.get("speech_style") or "informal"
            question = choose_form(ss, "Как прошло занятие?", "Как прошёл урок?")
            keyboard = make_lesson_feedback_keyboard(lesson["lesson_id"], speech_style=ss)
            await asyncio.wait_for(
                bot.send_message(
                    lesson["student_id"],
                    question,
                    reply_markup=keyboard,
                ),
                timeout=10,
            )
            await db.mark_feedback_request_sent(lesson["lesson_id"])
            sent += 1
        except Exception as exc:
            logger.warning("Ошибка отправки фидбэк-запроса для урока %s: %s", lesson["lesson_id"], exc)

    update_job_status("lesson_feedback_request", "ok", sent=sent, checked=len(lessons or []))
    write_runtime_event("lesson_feedback_request", "ok", sent=sent, checked=len(lessons or []))


def setup_scheduler(bot, db: "Database") -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TUTORBOT_TIMEZONE)
    scheduler.add_job(
        lesson_completion_job,
        CronTrigger(hour=0, minute=30),
        args=[bot, db],
        id="lesson_completion",
        name="Авто-завершение прошедших уроков и списание баланса",
    )
    scheduler.add_job(
        payment_reminder_job,
        CronTrigger(day_of_week="sun", hour=11, minute=0),
        args=[bot, db, "morning"],
        id="payment_reminder_morning",
        name="Воскресное мягкое напоминание об оплате",
    )
    scheduler.add_job(
        payment_reminder_job,
        CronTrigger(day_of_week="sun", hour=22, minute=0),
        args=[bot, db, "evening"],
        id="payment_reminder_evening",
        name="Воскресное вечернее напоминание об оплате",
    )
    scheduler.add_job(
        review_request_job,
        CronTrigger(hour=12, minute=0),
        args=[bot, db],
        id="review_request",
        name="Запрос отзыва после 3 недель занятий",
    )
    scheduler.add_job(
        homework_reminder_job,
        CronTrigger(hour=20, minute=0),
        args=[bot, db],
        id="homework_reminder",
        name="Напоминание о ДЗ с дедлайном завтра",
    )
    scheduler.add_job(
        queued_homework_delivery_job,
        CronTrigger(minute="*/5"),
        args=[bot, db],
        id="queued_homework_delivery",
        name="Отложенная отправка домашки",
    )
    scheduler.add_job(
        homework_gap_check_job,
        CronTrigger(minute=15),
        args=[bot, db],
        id="homework_gap_check",
        name="Проверка, задано ли ДЗ перед ближайшим уроком",
    )
    scheduler.add_job(
        lesson_reminder_job,
        CronTrigger(minute="*/5"),
        args=[bot, db],
        id="lesson_reminder",
        name="Напоминание о занятии (онлайн 10м, очно 60м)",
    )
    scheduler.add_job(
        teacher_lesson_followup_job,
        CronTrigger(minute="*/5"),
        args=[bot, db],
        id="teacher_lesson_followup",
        name="Teacher follow-up после урока",
    )
    scheduler.add_job(
        first_lesson_payment_invite_job,
        CronTrigger(minute="*/5"),
        args=[bot, db],
        id="first_lesson_payment_invite",
        name="Реквизиты после первого урока (для новых учеников)",
    )
    scheduler.add_job(
        teacher_bookmark_reminder_job,
        CronTrigger(minute="*/5"),
        args=[bot, db],
        id="teacher_bookmark_reminder",
        name="Teacher reminder с закладкой перед уроком",
    )
    scheduler.add_job(
        parent_weekly_digest_job,
        CronTrigger(day_of_week="sun", hour=18, minute=0),
        args=[bot, db],
        id="parent_weekly_digest",
        name="Еженедельная сводка для родителей",
    )
    scheduler.add_job(
        study_plan_weekly_digest_job,
        CronTrigger(day_of_week="sun", hour=19, minute=0),
        args=[bot, db],
        id="study_plan_weekly_digest",
        name="Еженедельный обзор учебного плана",
    )
    scheduler.add_job(
        calendar_sync_job,
        CronTrigger(minute="0,30"),
        args=[bot, db],
        id="calendar_auto_sync",
        name="Авто-синхронизация Google Calendar",
    )
    scheduler.add_job(
        user_journey_dispatch_job,
        CronTrigger(minute="*/30"),
        args=[bot, db],
        id="user_journey_dispatch",
        name="Онбординг: рассылка журнальных событий",
    )
    scheduler.add_job(
        pair_weekly_report_job,
        CronTrigger(day_of_week="mon", hour=10, minute=0),
        args=[bot, db],
        id="pair_weekly_report",
        name="Еженедельный обзор для пар",
    )
    scheduler.add_job(
        morning_briefing_job,
        CronTrigger(hour=9, minute=0),
        args=[bot, db],
        id="morning_briefing",
        name="Утренняя сводка: уроки и проблемы",
    )
    scheduler.add_job(
        homework_nudge_job,
        CronTrigger(minute="0,30"),
        args=[bot, db],
        id="homework_nudge",
        name="ДЗ-надзиратель: напоминание об отправке ДЗ",
    )
    if config.TOUCHES_ENABLED:
        scheduler.add_job(
            between_lesson_touches_job,
            CronTrigger(hour=config.TOUCHES_RUN_HOUR, minute=config.TOUCHES_RUN_MINUTE),
            args=[bot, db],
            id="between_lesson_touches",
            name="Межурочные касания (раз в день)",
        )
    else:
        logger.warning("between_lesson_touches_job отключён через TOUCHES_ENABLED=false")
    scheduler.add_job(
        achievement_check_job,
        CronTrigger(hour=1, minute=0),
        args=[bot, db],
        id="achievement_check",
        name="Проверка достижений учеников",
    )
    scheduler.add_job(
        achievement_notify_job,
        CronTrigger(hour=9, minute=15),
        args=[bot, db],
        id="achievement_notify",
        name="Отправка поздравлений с достижениями",
    )
    scheduler.add_job(
        lesson_feedback_request_job,
        CronTrigger(minute="*/15"),
        args=[bot, db],
        id="lesson_feedback_request",
        name="Запрос фидбэка после урока",
    )
    return scheduler
