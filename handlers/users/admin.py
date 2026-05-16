import asyncio
import logging
import subprocess
from datetime import datetime

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from handlers.users.admin_sections.common import (
    get_message_origin,
    is_admin as _is_admin,
    parse_admin_student_picker_callback_data,
    q as _q,
    render_admin_student_picker,
    restore_admin_view,
)
from handlers.users.screens import render_user_home
from keyboards.inline import (
    FREEZE_REASON_LABELS,
    admin_keyboard,
    admin_service_keyboard,
    admin_students_keyboard,
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_admin_context_keyboard,
    make_admin_education_keyboard,
    make_admin_parent_picker_keyboard,
    make_admin_preview_hub_keyboard,
    make_back_button_keyboard,
    make_brand_tone_keyboard,
    make_freeze_queue_keyboard,
    make_lesson_delete_confirm_keyboard,
    make_lessons_manage_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import AdminAddLesson, AdminBlockTelegramId, AdminManageLessons
from utils.brand import brand_tone_label, get_brand_tone, set_brand_tone
from utils.db_api.postgresql import Database
from utils.google_calendar import (
    delete_calendar_event,
    format_sync_report_html,
    load_last_sync_report,
    sync_calendar_to_db,
)
from utils.observability import load_ops_status
from utils.preview_mode import (
    clear_admin_preview_session,
    get_preview_context,
    preview_role_label,
    set_admin_preview_session,
)
from utils.speech import choose_form
from utils.telegram_actions import with_chat_action
from utils.ui_text import (
    ADMIN_ADD_LESSON_INVALID_TEXT,
    ADMIN_ADD_LESSON_PROMPT_TEXT,
    ADMIN_ADD_LESSON_START_TEXT,
    build_admin_freeze_action_text,
    build_admin_freeze_queue_text,
    build_admin_freeze_request_text,
    build_admin_dashboard_text,
    build_brand_tone_text,
    ADMIN_EDUCATION_CATEGORY_TEXT,
    ADMIN_HOME_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    ADMIN_SERVICE_CATEGORY_TEXT,
    ADMIN_STUDENTS_CATEGORY_TEXT,
    ADMIN_SYNC_ERROR_HINT,
    ADMIN_SYNC_IN_PROGRESS_TEXT,
)

logger = logging.getLogger(__name__)

router = Router()

ADMIN_PREVIEW_PARENT_PAGE_SIZE = 5

def _get_admin_category_views() -> dict:
    """Build category views dict; education keyboard is built with freeze count = 0 as default."""
    return {
        "students": (
            ADMIN_STUDENTS_CATEGORY_TEXT,
            admin_students_keyboard,
        ),
        "education": (
            ADMIN_EDUCATION_CATEGORY_TEXT,
            make_admin_education_keyboard(0),
        ),
        "service": (
            ADMIN_SERVICE_CATEGORY_TEXT,
            admin_service_keyboard,
        ),
    }


ADMIN_CATEGORY_VIEWS = _get_admin_category_views()


def _return_view_from_source(source: str | None) -> str:
    if source == "education":
        return "admin:cat:education"
    if source == "students":
        return "admin:cat:students"
    if source == "communication":
        return "admin:broadcast"
    if source == "service":
        return "admin:cat:service"
    return "admin:home"


def _reply_markup_for_return_view(return_view: str | None, student_id: int | None = None):
    if return_view and return_view.startswith("admin:student_card:"):
        parts = return_view.split(":")
        if len(parts) == 4 and student_id is not None:
            return make_admin_context_keyboard(student_id, int(parts[3]))
    return make_back_button_keyboard("◀️ Вернуться", return_view or "admin:home")


def _parse_admin_id_command(message_text: str | None) -> tuple[int | None, str]:
    parts = (message_text or "").strip().split(maxsplit=2)
    if len(parts) < 2:
        return None, ""

    try:
        telegram_id = int(parts[1])
    except ValueError:
        return None, ""

    if telegram_id <= 0:
        return None, ""

    reason = parts[2].strip() if len(parts) > 2 else ""
    return telegram_id, reason


def _parse_admin_block_payload(message_text: str | None) -> tuple[int | None, str]:
    parts = (message_text or "").strip().split(maxsplit=1)
    if not parts:
        return None, ""
    try:
        telegram_id = int(parts[0])
    except ValueError:
        return None, ""
    if telegram_id <= 0:
        return None, ""
    reason = parts[1].strip() if len(parts) > 1 else ""
    return telegram_id, reason


def _fix_utf8_mojibake(value: str) -> str:
    try:
        return value.encode("cp1251").decode("utf-8")
    except Exception:
        return value


def _format_block_entry_label(item: dict | None) -> str:
    if not item:
        return "нет в базе"
    full_name = item.get("full_name")
    role = item.get("role")
    if full_name and role:
        return f"{_q(full_name)} ({_q(role)})"
    if full_name:
        return _q(full_name)
    if role:
        return _q(role)
    return "нет в базе"


def _format_blocked_ids_text(rows: list[dict]) -> str:
    if not rows:
        return "🚫 <b>Блокировки по Telegram ID</b>\n\nСписок пока пуст."

    lines = [
        "🚫 <b>Блокировки по Telegram ID</b>",
        "",
        f"Показано: <b>{len(rows)}</b>",
    ]
    for index, row in enumerate(rows, 1):
        blocked_at = row.get("blocked_at")
        blocked_at_label = blocked_at.strftime("%d.%m.%Y %H:%M") if blocked_at else "-"
        role = row.get("role") or "нет профиля"
        status = "неактивен" if row.get("is_active") is False else "активен"
        reason = row.get("reason") or "без причины"
        lines.extend([
            "",
            f"{index}. <code>{row['telegram_id']}</code>  |  <b>{_format_block_entry_label(row)}</b>",
            f"Статус профиля: <b>{_q(role)}</b>, {status}",
            f"Когда: <b>{blocked_at_label}</b>",
            f"Причина: <b>{_q(reason)}</b>",
        ])
    return "\n".join(lines)


def _admin_blocked_keyboard(rows: list[dict]) -> InlineKeyboardMarkup:
    keyboard_rows = [
        [InlineKeyboardButton(text="➕ Заблокировать ID", callback_data="admin:blocked:add")]
    ]
    for row in rows:
        telegram_id = int(row["telegram_id"])
        keyboard_rows.append([
            InlineKeyboardButton(
                text=f"✅ Снять блокировку {telegram_id}",
                callback_data=f"admin:blocked:unblock:{telegram_id}",
            )
        ])
    keyboard_rows.append([InlineKeyboardButton(text="◀️ К сервису", callback_data="admin:cat:service")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def _render_admin_blocked(message: types.Message, db: Database):
    rows = list(await db.get_blocked_telegram_ids(limit=20) or [])
    await message.edit_text(
        _format_blocked_ids_text(rows),
        reply_markup=_admin_blocked_keyboard(rows),
    )


async def render_admin_home(message: types.Message, db: Database):
    snapshot = await db.get_admin_dashboard_snapshot()
    ops_status = load_ops_status()
    sync_report = load_last_sync_report()
    await message.edit_text(
        build_admin_dashboard_text(snapshot, ops_status, sync_report),
        reply_markup=admin_keyboard,
    )


async def render_admin_category(message: types.Message, category: str, db: Database | None = None):
    if category == "education" and db is not None:
        pending = await db.get_pending_freeze_lessons()
        keyboard = make_admin_education_keyboard(len(pending or []))
        await message.edit_text(ADMIN_EDUCATION_CATEGORY_TEXT, reply_markup=keyboard)
        return

    view = ADMIN_CATEGORY_VIEWS.get(category)
    if not view:
        await message.edit_text("⚠️ Раздел не найден.", reply_markup=back_to_admin_keyboard)
        return

    text, keyboard = view
    await message.edit_text(text, reply_markup=keyboard)


async def render_brand_tone_settings(message: types.Message):
    current_tone = get_brand_tone()
    await message.edit_text(
        build_brand_tone_text(current_tone),
        reply_markup=make_brand_tone_keyboard(current_tone, back_callback="admin:cat:service"),
    )


async def render_admin_service_monitoring(message: types.Message):
    """Kept for backward compatibility — now renders the flat service screen."""
    await message.edit_text(
        ADMIN_SERVICE_CATEGORY_TEXT,
        reply_markup=admin_service_keyboard,
    )


async def render_admin_service_context(message: types.Message):
    """Kept for backward compatibility — now renders the flat service screen."""
    await message.edit_text(
        ADMIN_SERVICE_CATEGORY_TEXT,
        reply_markup=admin_service_keyboard,
    )


async def render_admin_preview_hub(message: types.Message, db: Database, admin_id: int):
    preview = await get_preview_context(db, admin_id)
    lines = [
        "🧪 <b>Просмотр ролей</b>",
        "",
        "Выберите профиль, чтобы открыть пользовательский контур от его лица.",
        "Если родителей в базе пока нет, раздел «Как родитель» предложит выбрать ученика и построит просмотр на его данных.",
        "Это безопасный режим просмотра: экраны и переходы работают, но изменения не сохраняются.",
    ]
    if preview:
        lines.extend([
            "",
            f"Сейчас открыт: <b>{preview_role_label(preview.get('role'))}</b> — <b>{_q(preview.get('full_name'))}</b>",
        ])
    await message.edit_text(
        "\n".join(lines),
        reply_markup=make_admin_preview_hub_keyboard(has_active_preview=bool(preview)),
    )


async def render_admin_parent_preview_picker(message: types.Message, db: Database, page: int = 0):
    parents = await db.get_parents_overview()
    if not parents:
        await render_admin_student_picker(message, db, flow="preview_parent", page=0)
        return

    start = page * ADMIN_PREVIEW_PARENT_PAGE_SIZE + 1
    finish = min(len(parents), (page + 1) * ADMIN_PREVIEW_PARENT_PAGE_SIZE)
    await message.edit_text(
        "\n".join([
            "👨‍👩‍👧 <b>Просмотр как родитель</b>",
            "",
            f"Показываю профили {start}–{finish} из {len(parents)}.",
            "В строке указано: <b>связанных детей / всех детей</b>.",
        ]),
        reply_markup=make_admin_parent_picker_keyboard(parents, page, ADMIN_PREVIEW_PARENT_PAGE_SIZE),
    )


async def render_admin_freeze_queue(
    message: types.Message,
    db: Database,
    page: int = 0,
    flash_text: str | None = None,
):
    pending = list(await db.get_pending_freeze_lessons() or [])
    if not pending:
        text = build_admin_freeze_queue_text(0)
        if flash_text:
            text = f"{flash_text}\n\n{text}"
        await message.edit_text(
            text,
            reply_markup=make_back_button_keyboard("◀️ К учебному процессу", "admin:cat:education"),
        )
        return

    page = max(0, min(page, len(pending) - 1))
    lesson = pending[page]
    date_str = (
        lesson["freeze_start_date"].strftime("%d.%m.%Y %H:%M")
        if lesson.get("freeze_start_date") else "—"
    )
    reason_label = FREEZE_REASON_LABELS.get(lesson.get("freeze_reason"), lesson.get("freeze_reason") or "—")
    blocks = [build_admin_freeze_queue_text(len(pending), page + 1)]
    if flash_text:
        blocks.append(flash_text)
    blocks.append(
        build_admin_freeze_request_text(
            lesson["id"],
            lesson["full_name"],
            reason_label,
            date_str,
        )
    )
    await message.edit_text(
        "\n\n".join(blocks),
        reply_markup=make_freeze_queue_keyboard(lesson["id"], page, len(pending)),
    )


# ─── /admin command ───────────────────────────────────────────────────────────

@router.message(Command('admin'))
async def command_admin(message: types.Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    snapshot = await db.get_admin_dashboard_snapshot()
    ops_status = load_ops_status()
    sync_report = load_last_sync_report()
    await message.answer(
        build_admin_dashboard_text(snapshot, ops_status, sync_report),
        reply_markup=admin_keyboard,
    )


# ─── /sync command ────────────────────────────────────────────────────────────

@router.message(Command('sync'))
async def command_sync(message: types.Message, db: Database):
    if not _is_admin(message.from_user.id):
        return
    await message.answer(ADMIN_SYNC_IN_PROGRESS_TEXT)
    try:
        async with with_chat_action(message, "typing"):
            report = await sync_calendar_to_db(db)
        await message.answer(format_sync_report_html(report))
    except Exception as e:
        logger.error(f"Ошибка синхронизации Calendar: {e}")
        await message.answer(
            f"❌ Ошибка синхронизации:\n<code>{e}</code>\n\n"
            f"{ADMIN_SYNC_ERROR_HINT}"
        )


# ─── /restart command ────────────────────────────────────────────────────────

@router.message(Command('restart'))
async def command_restart(message: types.Message):
    if not _is_admin(message.from_user.id):
        return
    from keyboards.inline import InlineKeyboardMarkup, InlineKeyboardButton
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, перезапустить", callback_data="admin:restart:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin:home"),
        ],
    ])
    await message.answer(
        "🔄 <b>Перезапуск бота</b>\n\n"
        "Бот будет недоступен несколько секунд.\n"
        "Вы уверены?",
        reply_markup=confirm_kb,
    )


# ─── Back to admin panel ──────────────────────────────────────────────────────

@router.message(Command('block'))
async def command_block(message: types.Message, db: Database):
    if not _is_admin(message.from_user.id):
        return

    telegram_id, reason = _parse_admin_id_command(message.text)
    if telegram_id is None:
        await message.answer("🚫 <b>Формат команды</b>\n\n<code>/block 123456789 причина</code>")
        return

    if telegram_id == message.from_user.id:
        await message.answer("⚠️ Свой Telegram ID блокировать нельзя.")
        return

    existing_user = await db.get_user(telegram_id)
    was_blocked = await db.is_telegram_id_blocked(telegram_id)
    await db.block_telegram_id(
        telegram_id,
        blocked_by=message.from_user.id,
        reason=reason or None,
    )

    lines = [
        "🚫 <b>ID заблокирован</b>",
        "",
        f"Telegram ID: <code>{telegram_id}</code>",
        f"Профиль: <b>{_format_block_entry_label(existing_user)}</b>",
    ]
    if reason:
        lines.append(f"Причина: <b>{_q(reason)}</b>")
    if was_blocked:
        lines.append("Запись обновлена.")
    elif existing_user:
        if existing_user.get("is_active") is False:
            lines.append("Профиль уже был неактивен. Блок по ID добавлен поверх этого состояния.")
        else:
            lines.append("Профиль дополнительно деактивирован, чтобы остановить доступ и рабочие напоминания.")
    else:
        lines.append("Если этот ID впервые напишет боту, регистрация не начнётся.")
    await message.answer("\n".join(lines))


@router.message(Command('unblock'))
async def command_unblock(message: types.Message, db: Database):
    if not _is_admin(message.from_user.id):
        return

    telegram_id, _ = _parse_admin_id_command(message.text)
    if telegram_id is None:
        await message.answer("✅ <b>Формат команды</b>\n\n<code>/unblock 123456789</code>")
        return

    block_entry = await db.get_telegram_block(telegram_id)
    if not block_entry:
        await message.answer(f"⚠️ ID <code>{telegram_id}</code> нет в списке блокировок.")
        return

    result = await db.unblock_telegram_id(telegram_id)
    lines = [
        "✅ <b>Блокировка снята</b>",
        "",
        f"Telegram ID: <code>{telegram_id}</code>",
        f"Профиль: <b>{_format_block_entry_label(block_entry)}</b>",
    ]
    if block_entry.get("reason"):
        lines.append(f"Прежняя причина: <b>{_q(block_entry.get('reason'))}</b>")
    if result.get("reactivated"):
        lines.append("Профиль снова активирован.")
    else:
        lines.append("Жёсткая блокировка по ID снята. Если профиль был неактивен раньше, он так и останется выключенным.")
    await message.answer("\n".join(lines))


@router.message(Command('blocked'))
async def command_blocked(message: types.Message, db: Database):
    if not _is_admin(message.from_user.id):
        return

    rows = list(await db.get_blocked_telegram_ids(limit=20) or [])
    await message.answer(_format_blocked_ids_text(rows), reply_markup=_admin_blocked_keyboard(rows))


@router.callback_query(lambda c: c.data == "admin:blocked")
async def admin_blocked(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_blocked(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:blocked:add", StateFilter("*"))
async def admin_blocked_add_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    await state.set_state(AdminBlockTelegramId.waiting_for_target)
    await callback_query.message.edit_text(
        "🚫 <b>Заблокировать Telegram ID</b>\n\n"
        "Отправьте ID и причину одним сообщением:\n"
        "<code>123456789 причина</code>",
        reply_markup=make_back_button_keyboard("◀️ К блокировкам", "admin:blocked"),
    )
    await callback_query.answer()


@router.message(StateFilter(AdminBlockTelegramId.waiting_for_target))
async def admin_blocked_add_text(message: types.Message, state: FSMContext, db: Database):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    telegram_id, reason = _parse_admin_block_payload(message.text)
    if telegram_id is None:
        await message.answer(
            "⚠️ Отправьте Telegram ID и, при необходимости, причину:\n"
            "<code>123456789 причина</code>",
            reply_markup=make_back_button_keyboard("◀️ К блокировкам", "admin:blocked"),
        )
        return
    if telegram_id == message.from_user.id:
        await message.answer(
            "⚠️ Свой Telegram ID блокировать нельзя.",
            reply_markup=make_back_button_keyboard("◀️ К блокировкам", "admin:blocked"),
        )
        return

    existing_user = await db.get_user(telegram_id)
    was_blocked = await db.is_telegram_id_blocked(telegram_id)
    await db.block_telegram_id(
        telegram_id,
        blocked_by=message.from_user.id,
        reason=reason or None,
    )
    await state.clear()

    lines = [
        "🚫 <b>ID заблокирован</b>",
        "",
        f"Telegram ID: <code>{telegram_id}</code>",
        f"Профиль: <b>{_format_block_entry_label(existing_user)}</b>",
    ]
    if reason:
        lines.append(f"Причина: <b>{_q(reason)}</b>")
    if was_blocked:
        lines.append("Запись обновлена.")
    elif existing_user and existing_user.get("is_active") is not False:
        lines.append("Профиль дополнительно деактивирован.")
    await message.answer("\n".join(lines), reply_markup=make_back_button_keyboard("◀️ К блокировкам", "admin:blocked"))


@router.callback_query(lambda c: c.data and c.data.startswith("admin:blocked:unblock:"))
async def admin_blocked_unblock(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    try:
        telegram_id = int(callback_query.data.split(":")[3])
    except (IndexError, ValueError):
        await callback_query.answer("Некорректный ID.", show_alert=True)
        return

    block_entry = await db.get_telegram_block(telegram_id)
    if not block_entry:
        await callback_query.answer("Этой блокировки уже нет.", show_alert=True)
        await _render_admin_blocked(callback_query.message, db)
        return

    await db.unblock_telegram_id(telegram_id)
    await _render_admin_blocked(callback_query.message, db)
    await callback_query.answer("Блокировка снята.")


@router.callback_query(lambda c: c.data in {'back_to_admin', 'admin:home'}, StateFilter('*'))
async def back_to_admin(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    await render_admin_home(callback_query.message, db)
    await callback_query.answer()


_ADMIN_TOP_LEVEL_CATEGORIES = {"admin:cat:students", "admin:cat:education", "admin:cat:service"}


@router.callback_query(lambda c: c.data in _ADMIN_TOP_LEVEL_CATEGORIES)
async def admin_open_category(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    # Strip to top-level category (e.g. "admin:cat:education" → "education")
    parts = callback_query.data.split(':', 2)
    category = parts[2] if len(parts) > 2 else ""

    if not category:
        await callback_query.answer("Раздел не найден.", show_alert=True)
        return

    await render_admin_category(callback_query.message, category, db=db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:sync'))
async def admin_sync_callback(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    back_target = "admin:cat:service" if source in {"monitoring", "service"} else _return_view_from_source(source)
    back_keyboard = make_back_button_keyboard(
        "◀️ К сервису" if back_target == "admin:cat:service" else "◀️ Вернуться",
        back_target,
    )

    await callback_query.message.edit_text(
        ADMIN_SYNC_IN_PROGRESS_TEXT,
        reply_markup=back_keyboard,
    )
    try:
        report = await sync_calendar_to_db(db)
        await callback_query.message.edit_text(
            format_sync_report_html(report),
            reply_markup=back_keyboard,
        )
    except Exception as e:
        logger.error(f"Ошибка синхронизации Calendar: {e}")
        await callback_query.message.edit_text(
            f"❌ Ошибка синхронизации:\n<code>{e}</code>\n\n"
            f"{ADMIN_SYNC_ERROR_HINT}",
            reply_markup=back_keyboard,
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'admin:calendar_report')
async def admin_calendar_report(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    from handlers.users.admin_sections.calendar_aliases import _build_calendar_sync_snapshot_lines

    await callback_query.message.edit_text(
        "\n".join(["📋 <b>Краткий отчёт синхронизации</b>", *_build_calendar_sync_snapshot_lines()]) or "Отчёта пока нет.",
        reply_markup=make_back_button_keyboard("◀️ К сервису", "admin:cat:service"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'admin:brand_tone')
async def admin_brand_tone(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await render_brand_tone_settings(callback_query.message)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:brand_tone_set:'))
async def admin_brand_tone_set(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    tone = callback_query.data.split(':', 3)[3]
    current_tone = set_brand_tone(tone)
    await render_brand_tone_settings(callback_query.message)
    await callback_query.answer(f"Тональность: {brand_tone_label(current_tone)}")


@router.callback_query(lambda c: c.data == "admin:preview")
async def admin_preview_hub(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await render_admin_preview_hub(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:preview:students")
async def admin_preview_students(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await render_admin_student_picker(callback_query.message, db, flow="preview_student", page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:preview:parents")
async def admin_preview_parents(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await render_admin_parent_preview_picker(callback_query.message, db, page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:preview:parents:page:"))
async def admin_preview_parents_page(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    page = int(callback_query.data.split(":")[4])
    await render_admin_parent_preview_picker(callback_query.message, db, page=page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_pick_select:preview_student:"))
async def admin_preview_student_selected(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, student_id, _ = parse_admin_student_picker_callback_data(callback_query.data)
    student = await db.get_user(student_id)
    if not student or student.get("role") != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    set_admin_preview_session(
        callback_query.from_user.id,
        student_id,
        "student",
        student.get("full_name") or str(student_id),
    )
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer("Открыл просмотр ученика.")


@router.callback_query(lambda c: c.data.startswith("admin:student_pick_select:preview_parent:"))
async def admin_preview_parent_from_student_selected(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, student_id, _ = parse_admin_student_picker_callback_data(callback_query.data)
    student = await db.get_user(student_id)
    if not student or student.get("role") != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    student_name = student.get("full_name") or str(student_id)
    set_admin_preview_session(
        callback_query.from_user.id,
        callback_query.from_user.id,
        "parent",
        f"Родитель ученика {student_name}",
        synthetic_parent_student_id=student_id,
    )
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer("Открыл просмотр родителя по ученику.")


@router.callback_query(lambda c: c.data.startswith("admin:parent_preview_select:"))
async def admin_preview_parent_selected(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(":")
    parent_id = int(parts[2])
    parent = await db.get_user(parent_id)
    if not parent or parent.get("role") != "parent" or parent.get("is_active") is False:
        await callback_query.answer("Родитель не найден.", show_alert=True)
        return

    set_admin_preview_session(
        callback_query.from_user.id,
        parent_id,
        "parent",
        parent.get("full_name") or str(parent_id),
    )
    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer("Открыл просмотр родителя.")


@router.callback_query(lambda c: c.data == "admin:preview:open")
async def admin_preview_open(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    preview = await get_preview_context(db, callback_query.from_user.id)
    if not preview:
        await callback_query.answer("Активного режима просмотра сейчас нет.", show_alert=True)
        return

    await render_user_home(callback_query.message, db, callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:preview:stop", StateFilter('*'))
async def admin_preview_stop(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await state.clear()
    clear_admin_preview_session(callback_query.from_user.id)
    await render_admin_home(callback_query.message, db)
    await callback_query.answer("Режим просмотра выключен.")


# ─── Add lesson ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data.startswith('admin:add_lesson'))
async def admin_add_lesson_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':', 2)
    source = parts[2] if len(parts) > 2 else None
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)

    students = await db.get_all_students()

    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_REGISTERED_STUDENTS_TEXT,
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await state.clear()
    await state.update_data(
        admin_return_view=_return_view_from_source(source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddLesson.waiting_for_lesson_student)
    await render_admin_student_picker(callback_query.message, db, flow="add_lesson", page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:quick:add_lesson:'))
async def admin_add_lesson_quick(callback_query: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback_query.from_user.id):
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
        admin_return_view=(
            f"admin:student_{source}:{student_id}:{page}"
            if source in {"actions", "settings", "danger"}
            else f"admin:student_card:{student_id}:{page}"
        ),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminAddLesson.waiting_for_lesson_date)
    await callback_query.message.edit_text(
        ADMIN_ADD_LESSON_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:') or c.data.startswith("admin:student_pick_select:add_lesson:"),
    StateFilter(AdminAddLesson.waiting_for_lesson_student),
)
async def admin_lesson_student_selected(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data.startswith("admin:student_pick_select:"):
        _, student_id, _ = parse_admin_student_picker_callback_data(callback_query.data)
    else:
        student_id = int(callback_query.data.split(':')[1])
    await state.update_data(student_id=student_id)
    await state.set_state(AdminAddLesson.waiting_for_lesson_date)
    await callback_query.message.edit_text(
        ADMIN_ADD_LESSON_PROMPT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddLesson.waiting_for_lesson_date))
async def admin_lesson_date_entered(message: types.Message, state: FSMContext, db: Database):
    try:
        lesson_date = datetime.strptime((message.text or "").strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(
            ADMIN_ADD_LESSON_INVALID_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data['student_id']
    return_view = data.get("admin_return_view")
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await db.add_lesson(student_id, lesson_date)

    student = await db.get_user(student_id)
    student_name = _q(student['full_name']) if student else str(student_id)

    await state.clear()
    await restore_admin_view(message.bot, db, origin_chat_id, origin_message_id, return_view)
    await message.answer(
        f"✅ <b>Занятие добавлено</b>\n\n"
        f"👤 Ученик: {student_name}\n"
        f"📅 Дата: {lesson_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Карточка и сводка уже обновлены.",
        reply_markup=_reply_markup_for_return_view(return_view, student_id),
    )

# ─── Freeze requests ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'admin:freezes')
async def admin_freezes(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await render_admin_freeze_queue(callback_query.message, db, page=0)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('admin:freezes:page:'))
async def admin_freezes_page(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    page = int(callback_query.data.split(':')[3])
    await render_admin_freeze_queue(callback_query.message, db, page=page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('freeze_action:'))
async def admin_freeze_action(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    _, action, lesson_id_str = parts[:3]
    page = int(parts[3]) if len(parts) > 3 else 0
    lesson_id = int(lesson_id_str)

    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow('SELECT * FROM lessons WHERE id = $1', lesson_id)

    if not lesson:
        await callback_query.message.edit_text(
            "⚠️ Заявка не найдена.",
            reply_markup=make_back_button_keyboard("◀️ К заморозкам", "admin:freezes"),
        )
        await callback_query.answer()
        return

    student_tid = lesson['student_id']
    student = await db.get_user(student_tid)
    student_name = student['full_name'] if student else str(student_tid)

    if action == 'approve':
        await db.approve_freeze(lesson_id)
        lesson_date_str = (
            lesson['lesson_date'].strftime('%d.%m.%Y %H:%M')
            if lesson.get('lesson_date') else "дата уточняется"
        )
        flash_text = build_admin_freeze_action_text("approve", student_name, lesson_date_str)
        await callback_query.bot.send_message(
            student_tid,
            f"✅ <b>{choose_form(student.get('speech_style') if student else None, 'Ваша', 'Твоя')} заявка на заморозку одобрена!</b>\n\n"
            f"📅 Занятие заморожено: <b>{lesson_date_str}</b>\n\n"
            f"Когда {choose_form(student.get('speech_style') if student else None, 'будете', 'будешь')} готовы продолжить — {choose_form(student.get('speech_style') if student else None, 'сообщите', 'сообщи')} преподавателю.",
            reply_markup=make_teacher_reply_keyboard("freeze"),
        )
    else:
        await db.reject_freeze(lesson_id)
        flash_text = build_admin_freeze_action_text("reject", student_name)
        await callback_query.bot.send_message(
            student_tid,
            f"❌ <b>{choose_form(student.get('speech_style') if student else None, 'Ваша', 'Твоя')} заявка на заморозку отклонена.</b>\n\n"
            f"Занятия продолжаются в обычном режиме. Если остались вопросы — {choose_form(student.get('speech_style') if student else None, 'свяжитесь', 'свяжись')} с преподавателем.",
            reply_markup=make_teacher_reply_keyboard("freeze"),
        )

    await render_admin_freeze_queue(callback_query.message, db, page=page, flash_text=flash_text)
    await callback_query.answer()


# ─── Manage lessons (delete) ──────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == 'admin:manage_lessons')
async def admin_manage_lessons_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(
            "⚠️ Нет зарегистрированных учеников.", reply_markup=back_to_admin_keyboard
        )
        await callback_query.answer()
        return

    await state.set_state(AdminManageLessons.waiting_for_student)
    await render_admin_student_picker(callback_query.message, db, flow="manage_lessons", page=0)
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('select_student:') or c.data.startswith("admin:student_pick_select:manage_lessons:"),
    StateFilter(AdminManageLessons.waiting_for_student),
)
async def admin_manage_lessons_student_selected(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    if callback_query.data.startswith("admin:student_pick_select:"):
        _, student_id, _ = parse_admin_student_picker_callback_data(callback_query.data)
    else:
        student_id = int(callback_query.data.split(':')[1])
    student = await db.get_user(student_id)
    name = _q(student['full_name']) if student else str(student_id)

    lessons = await db.get_non_completed_lessons(student_id)
    await state.clear()

    if not lessons:
        await callback_query.message.edit_text(
            f"📅 У <b>{name}</b> нет активных занятий для удаления.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await callback_query.message.edit_text(
        f"🗑 <b>Занятия ученика {name}</b>\n\nВыберите занятие для удаления:",
        reply_markup=make_lessons_manage_keyboard(lessons),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_pick:"))
async def admin_student_picker_page(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    parts = callback_query.data.split(":")
    flow = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    await render_admin_student_picker(callback_query.message, db, flow=flow, page=page)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('lesson_delete_confirm:'))
async def admin_lesson_delete_confirm(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    lesson_id = int(callback_query.data.split(':')[1])
    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow('SELECT * FROM lessons WHERE id = $1', lesson_id)

    if not lesson:
        await callback_query.message.edit_text("⚠️ Занятие не найдено.", reply_markup=back_to_admin_keyboard)
        await callback_query.answer()
        return

    date_str = lesson['lesson_date'].strftime('%d.%m.%Y %H:%M') if lesson.get('lesson_date') else '—'
    has_calendar_link = bool(lesson.get('google_event_id'))
    calendar_hint = (
        "\n🗓 Событие связано с Google Calendar."
        "\nЕсли удалить только из базы бота, при следующей синхронизации урок может появиться снова.\n"
        if has_calendar_link else
        "\n🗓 Урок существует только в базе бота.\n"
    )
    await callback_query.message.edit_text(
        f"🗑 <b>Удалить занятие?</b>\n\n"
        f"📅 Дата: <b>{date_str}</b>\n"
        f"Статус: {lesson['status']}\n"
        f"{calendar_hint}\n"
        "⚠️ Действие необратимо.",
        reply_markup=make_lesson_delete_confirm_keyboard(lesson_id, can_delete_from_calendar=has_calendar_link),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('lesson_delete:'))
async def admin_lesson_delete(callback_query: types.CallbackQuery, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(':')
    lesson_id = int(parts[1])
    delete_mode = parts[2] if len(parts) > 2 else "db"

    async with db.pool.acquire() as conn:
        lesson = await conn.fetchrow('SELECT * FROM lessons WHERE id = $1', lesson_id)

    if not lesson:
        await callback_query.message.edit_text(
            "⚠️ Занятие не найдено.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    calendar_result = None
    if delete_mode == "calendar":
        google_event_id = lesson.get("google_event_id")
        if not google_event_id:
            await callback_query.message.edit_text(
                "⚠️ Это занятие не связано с Google Calendar. Можно удалить его только из базы бота.",
                reply_markup=back_to_admin_keyboard,
            )
            await callback_query.answer()
            return
        try:
            calendar_result = await delete_calendar_event(google_event_id)
        except Exception as exc:
            logger.error("Не удалось удалить событие %s из Google Calendar: %s", google_event_id, exc)
            await callback_query.message.edit_text(
                "⚠️ Не удалось удалить событие из Google Calendar.\n\n"
                "Занятие в базе бота пока оставлено без изменений.",
                reply_markup=back_to_admin_keyboard,
            )
            await callback_query.answer()
            return

    await db.delete_lesson(lesson_id)

    if delete_mode == "calendar":
        if calendar_result == "not_found":
            result_text = (
                "✅ <b>Занятие удалено из базы бота.</b>\n\n"
                "В Google Calendar связанное событие уже отсутствовало."
            )
        else:
            result_text = "✅ <b>Занятие удалено из базы бота и Google Calendar.</b>"
    else:
        result_text = (
            "✅ <b>Занятие удалено только из базы бота.</b>\n\n"
            "Если оно связано с Google Calendar, при следующей синхронизации запись может появиться снова."
        )

    await callback_query.message.edit_text(
        result_text,
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()
