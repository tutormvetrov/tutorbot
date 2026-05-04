"""Homework Nudge Engine: 3-step escalation when HW hasn't been sent after a lesson."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from data import config
from keyboards.inline import make_nudge_keyboard
from utils.observability import update_job_status, write_runtime_event
from utils.pulse_engine import is_quiet_hours
from utils.ui_text import build_nudge_message

if TYPE_CHECKING:
    from utils.db_api.postgresql import Database

logger = logging.getLogger(__name__)

# Escalation thresholds (hours since lesson ended)
_STAGE_1_HOURS = 2
_STAGE_2_HOURS = 6
_STAGE_3_HOURS = 24


async def check_and_send_nudges(bot, db: "Database") -> dict:
    """Main entry for scheduler. Checks lessons needing nudges and sends escalating messages.

    Returns dict with counts: checked, created, escalated, sent.
    """
    now = datetime.now()

    if is_quiet_hours(now):
        update_job_status("homework_nudge", "ok", skipped_quiet=True, sent=0)
        write_runtime_event("homework_nudge", "ok", skipped_quiet=True, sent=0)
        return {"checked": 0, "created": 0, "escalated": 0, "sent": 0}

    since = now - timedelta(hours=24)
    lessons = await db.get_lessons_needing_nudge(since=since)

    checked = len(lessons) if lessons else 0
    created = 0
    escalated = 0
    sent = 0

    for lesson in (lessons or []):
        lesson_id = lesson["lesson_id"]
        student_id = lesson["student_id"]
        full_name = lesson["full_name"] or "---"
        lesson_date = lesson["lesson_date"]

        hours_since = (now - lesson_date).total_seconds() / 3600

        existing_nudge = await db.get_open_nudge_for_lesson(lesson_id)

        try:
            if existing_nudge is None and hours_since >= _STAGE_1_HOURS:
                # Create stage 1
                nudge_id = await db.create_nudge(student_id, lesson_id, stage=1)
                hours_display = int(hours_since)
                text = build_nudge_message(full_name, stage=1, hours_since=hours_display)
                keyboard = make_nudge_keyboard(student_id, nudge_id, stage=1)
                try:
                    await bot.send_message(config.ADMIN_ID, text, reply_markup=keyboard)
                except Exception as exc:
                    logger.warning("Не удалось отправить nudge stage 1 для %s: %s", full_name, exc)
                created += 1
                sent += 1

            elif existing_nudge is not None:
                current_stage = existing_nudge["stage"]
                nudge_id = existing_nudge["id"]

                if current_stage == 1 and hours_since >= _STAGE_2_HOURS:
                    # Escalate to stage 2
                    await db.escalate_nudge(nudge_id, new_stage=2)
                    hours_display = int(hours_since)
                    text = build_nudge_message(full_name, stage=2, hours_since=hours_display)
                    keyboard = make_nudge_keyboard(student_id, nudge_id, stage=2)
                    try:
                        await bot.send_message(config.ADMIN_ID, text, reply_markup=keyboard)
                    except Exception as exc:
                        logger.warning("Не удалось отправить nudge stage 2 для %s: %s", full_name, exc)
                    escalated += 1
                    sent += 1

                elif current_stage == 2 and hours_since >= _STAGE_3_HOURS:
                    # Escalate to stage 3
                    await db.escalate_nudge(nudge_id, new_stage=3)
                    hours_display = int(hours_since)
                    text = build_nudge_message(full_name, stage=3, hours_since=hours_display)
                    keyboard = make_nudge_keyboard(student_id, nudge_id, stage=3)
                    try:
                        await bot.send_message(config.ADMIN_ID, text, reply_markup=keyboard)
                    except Exception as exc:
                        logger.warning("Не удалось отправить nudge stage 3 для %s: %s", full_name, exc)
                    escalated += 1
                    sent += 1

        except Exception as exc:
            logger.warning("Ошибка обработки nudge для урока %s: %s", lesson_id, exc)

    update_job_status(
        "homework_nudge",
        "ok",
        checked=checked,
        created=created,
        escalated=escalated,
        sent=sent,
    )
    write_runtime_event(
        "homework_nudge",
        "ok",
        checked=checked,
        created=created,
        escalated=escalated,
        sent=sent,
    )
    return {"checked": checked, "created": created, "escalated": escalated, "sent": sent}


async def handle_hw_auto_resolve(db: "Database", student_id: int) -> int:
    """Called when new HW is created. Resolves all open nudges for that student.

    Returns count of resolved nudges.
    """
    count = await db.resolve_nudges_for_student(student_id, resolution="hw_sent")
    if count:
        logger.info("Авто-закрытие %d nudge(s) для ученика %s (ДЗ отправлено)", count, student_id)
    return count
