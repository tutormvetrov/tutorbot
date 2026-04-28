from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Iterable, Mapping

from aiogram import html

from keyboards.inline import make_teacher_reply_keyboard
from utils.homework_text import homework_body_html
from utils.time import business_now

QUIET_HOURS_START = time(0, 0)
QUIET_HOURS_END = time(10, 0)


def is_homework_quiet_hours(now: datetime | None = None) -> bool:
    current = now or business_now()
    current_time = current.timetz().replace(tzinfo=None)
    return QUIET_HOURS_START <= current_time < QUIET_HOURS_END


def next_homework_delivery_slot(now: datetime | None = None) -> datetime:
    current = (now or business_now()).replace(tzinfo=None)
    slot = current.replace(
        hour=QUIET_HOURS_END.hour,
        minute=QUIET_HOURS_END.minute,
        second=0,
        microsecond=0,
    )
    if current >= slot:
        return slot + timedelta(days=1)
    return slot


def format_delivery_time(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def delivery_badge(row: Mapping[str, object] | None) -> str:
    if not row:
        return ""
    deliver_after = row.get("queued_deliver_after")
    if not deliver_after:
        return ""
    return f"📨 На {format_delivery_time(deliver_after)}"


def delivery_status_text(row: Mapping[str, object] | None) -> str:
    if not row or not row.get("queued_deliver_after"):
        return "✅ Доставка: <b>очередь пуста</b>"

    deliver_after = format_delivery_time(row.get("queued_deliver_after"))
    last_error = str(row.get("queued_last_error") or "").strip()
    attempts = int(row.get("queued_attempts") or 0)
    kind = "новое ДЗ" if row.get("queued_delivery_kind") == "new" else "обновление"
    if last_error:
        return (
            "⚠️ Доставка: <b>ошибка последней попытки</b>\n"
            f"📨 Очередь: <b>{html.quote(kind)}</b> на <b>{deliver_after}</b>\n"
            f"🔁 Попыток: <b>{attempts}</b>\n"
            f"🧾 Ошибка: <b>{html.quote(last_error)}</b>"
        )
    return f"📨 Доставка: <b>{html.quote(kind)}</b> запланирована на <b>{deliver_after}</b>"


def build_single_homework_notification_text(homework: Mapping[str, object], delivery_kind: str) -> str:
    title = (
        "📚 <b>Новое домашнее задание</b>"
        if delivery_kind == "new"
        else "📚 <b>Домашнее задание обновлено</b>"
    )
    homework_html = homework_body_html(
        str(homework.get("title") or ""),
        str(homework.get("description") or ""),
        str(homework.get("attachment_name") or ""),
        str(homework.get("attachment_mime_type") or ""),
    ) or "—"
    deadline = homework.get("deadline")
    deadline_label = deadline.strftime("%d.%m.%Y") if isinstance(deadline, datetime) else "—"
    return (
        f"{title}\n\n"
        f"📝 Задание:\n{homework_html}\n"
        f"📅 Дедлайн: <b>{deadline_label}</b>"
    )


async def send_single_homework_notification(
    bot,
    homework: Mapping[str, object],
    delivery_kind: str,
    *,
    include_attachment: bool = False,
):
    student_id = int(homework["student_id"])
    attachment_file_id = str(homework.get("attachment_file_id") or "")
    if include_attachment and attachment_file_id:
        await bot.send_document(student_id, attachment_file_id)
    await bot.send_message(
        student_id,
        build_single_homework_notification_text(homework, delivery_kind),
        reply_markup=make_teacher_reply_keyboard("homework", int(homework["id"])),
    )


def build_batch_homework_notification_text(items: Iterable[Mapping[str, object]]) -> str:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for item in items:
        grouped["new" if str(item.get("delivery_kind") or "new") == "new" else "updated"].append(item)

    lines = [
        "📚 <b>Утренний пакет домашних заданий</b>",
        "",
        "Ниже собраны новые и обновлённые задания. Если у задания есть файл, он доступен внутри карточки ДЗ в боте.",
    ]

    sections = [
        ("new", "🆕 <b>Новые ДЗ</b>"),
        ("updated", "♻️ <b>Обновлённые ДЗ</b>"),
    ]
    for key, header in sections:
        section_items = grouped.get(key) or []
        if not section_items:
            continue
        lines.extend(["", header])
        for item in section_items:
            homework_html = homework_body_html(
                str(item.get("title") or ""),
                str(item.get("description") or ""),
                str(item.get("attachment_name") or ""),
                str(item.get("attachment_mime_type") or ""),
            ) or "—"
            deadline = item.get("deadline")
            deadline_label = deadline.strftime("%d.%m.%Y") if isinstance(deadline, datetime) else "—"
            lines.extend([
                "",
                f"• <b>До {deadline_label}</b>",
                homework_html,
            ])
        if any(item.get("include_attachment") and item.get("attachment_name") for item in section_items):
            lines.extend([
                "",
                "📎 У части заданий есть файлы. Их можно открыть из карточки нужного ДЗ.",
            ])

    return "\n".join(lines)


async def send_batched_homework_notification(bot, student_id: int, items: list[Mapping[str, object]]):
    await bot.send_message(
        student_id,
        build_batch_homework_notification_text(items),
        reply_markup=make_teacher_reply_keyboard("homework"),
    )
