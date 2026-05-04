import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from data import config
from data.config import load_teacher_info
from keyboards.inline import (
    back_to_menu_keyboard,
    freeze_keyboard,
    make_admin_today_keyboard,
    make_materials_keyboard,
    make_study_plan_keyboard,
)
from handlers.users.screens import get_profile_payload, get_user_home_payload
from utils.db_api.postgresql import Database
from utils.google_calendar import load_last_sync_report
from utils.observability import load_ops_status, load_recent_runtime_events
from utils.time import business_naive_now
from utils.ui_text import (
    build_action_result_text,
    build_freeze_intro_text,
    build_help_text,
    build_materials_text,
    build_study_plan_text,
    build_admin_today_text,
)

router = Router()
logger = logging.getLogger(__name__)


def _today_window() -> tuple[datetime, datetime]:
    now = business_naive_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start, today_start + timedelta(days=1)


def _get_materials_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return (
        contacts.get("materials_url", "")
        or contacts.get("filen_url", "")
        or info.get("materials_url", "")
        or info.get("filen_url", "")
    )


def _get_project_site_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("project_site_url", "") or info.get("project_site_url", "")


@router.message(Command("menu"))
async def command_menu(message: Message, db: Database):
    logger.info(f"Команда /menu от {message.from_user.id}")
    text, keyboard = await get_user_home_payload(db, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def command_help(message: Message):
    logger.info(f"Команда /help от {message.from_user.id}")
    await message.answer(build_help_text())


@router.message(Command("profile"))
async def command_profile(message: Message, db: Database):
    logger.info(f"Команда /profile от {message.from_user.id}")
    text, keyboard = await get_profile_payload(db, message.from_user.id)
    await message.answer(text, reply_markup=keyboard or back_to_menu_keyboard)


@router.message(Command("today"))
async def command_today(message: Message, db: Database):
    logger.info(f"Команда /today от {message.from_user.id}")
    if message.from_user.id != config.ADMIN_ID:
        text, keyboard = await get_user_home_payload(db, message.from_user.id)
        await message.answer(text, reply_markup=keyboard)
        return
    today_start, tomorrow_start = _today_window()
    snapshot = await db.get_admin_today_snapshot(today_start, tomorrow_start)
    await message.answer(
        build_admin_today_text(snapshot, today_start.date()),
        reply_markup=make_admin_today_keyboard(snapshot),
    )


@router.message(Command("pulse"))
async def command_pulse(message: Message, db: Database):
    logger.info(f"Команда /pulse от {message.from_user.id}")
    if message.from_user.id != config.ADMIN_ID:
        text, keyboard = await get_user_home_payload(db, message.from_user.id)
        await message.answer(text, reply_markup=keyboard)
        return

    from utils.pulse_engine import compute_all_health, build_pulse_text
    from keyboards.inline import make_pulse_keyboard
    from utils.observability import load_ops_status as _load_ops

    # Handle /pulse off and /pulse on
    raw_text = (message.text or "").strip()
    parts = raw_text.split(maxsplit=1)
    if len(parts) == 2:
        arg = parts[1].lower()
        if arg == "off":
            ops = _load_ops()
            ops["pulse_enabled"] = False
            import json
            from pathlib import Path
            ops_path = Path(__file__).resolve().parents[2] / "data" / "ops_status.json"
            ops_path.write_text(json.dumps(ops, ensure_ascii=False, indent=2), encoding="utf-8")
            await message.answer("📊 Пульс отключён. Утренняя сводка не будет приходить.\nВключить: /pulse on")
            return
        elif arg == "on":
            ops = _load_ops()
            ops["pulse_enabled"] = True
            import json
            from pathlib import Path
            ops_path = Path(__file__).resolve().parents[2] / "data" / "ops_status.json"
            ops_path.write_text(json.dumps(ops, ensure_ascii=False, indent=2), encoding="utf-8")
            await message.answer("📊 Пульс включён. Утренняя сводка будет приходить в 09:00.")
            return

    health_list = await compute_all_health(db)
    text = build_pulse_text(health_list)
    keyboard = make_pulse_keyboard(health_list)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("freeze"))
async def command_freeze(message: Message, db: Database):
    logger.info(f"Команда /freeze от {message.from_user.id}")
    user_id = message.from_user.id
    if user_id == config.ADMIN_ID:
        from keyboards.inline import make_freeze_queue_keyboard, FREEZE_REASON_LABELS
        from utils.ui_text import build_admin_freeze_queue_text, build_admin_freeze_request_text
        from keyboards.inline import make_back_button_keyboard as _back_kb
        pending = list(await db.get_pending_freeze_lessons() or [])
        if not pending:
            await message.answer(
                build_admin_freeze_queue_text(0),
                reply_markup=_back_kb("◀️ К учебному процессу", "admin:cat:education"),
            )
        else:
            lesson = pending[0]
            date_str = (
                lesson["freeze_start_date"].strftime("%d.%m.%Y %H:%M")
                if lesson.get("freeze_start_date") else "—"
            )
            reason_label = FREEZE_REASON_LABELS.get(
                lesson.get("freeze_reason"), lesson.get("freeze_reason") or "—"
            )
            await message.answer(
                "\n\n".join([
                    build_admin_freeze_queue_text(len(pending), 1),
                    build_admin_freeze_request_text(
                        lesson["id"], lesson["full_name"], reason_label, date_str
                    ),
                ]),
                reply_markup=make_freeze_queue_keyboard(lesson["id"], 0, len(pending)),
            )
        return
    user = await db.get_user(user_id)
    if not user or user.get("role") == "parent":
        text, keyboard = await get_user_home_payload(db, user_id)
        await message.answer(text, reply_markup=keyboard)
        return
    from handlers.users.callbacks import _get_learning_student_id
    learning_user_id = await _get_learning_student_id(db, user_id)
    lessons = await db.get_active_lessons(learning_user_id)
    active_count = len(lessons)
    if not active_count:
        await message.answer(
            build_action_result_text(
                "Заморозка сейчас не нужна",
                "У вас нет активных занятий, которые можно отправить на заморозку.",
                next_step="Когда появятся новые уроки, к этой кнопке можно будет вернуться в любой момент.",
                icon="ℹ️",
            ),
            reply_markup=back_to_menu_keyboard,
        )
    else:
        await message.answer(build_freeze_intro_text(active_count), reply_markup=freeze_keyboard)


@router.message(Command("plan"))
async def command_plan(message: Message, db: Database):
    logger.info(f"Команда /plan от {message.from_user.id}")
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user or user.get("role") != "student":
        text, keyboard = await get_user_home_payload(db, user_id)
        await message.answer(text, reply_markup=keyboard)
        return
    from handlers.users.callbacks import _get_learning_student_id
    learning_user_id = await _get_learning_student_id(db, user_id)
    plan = await db.get_active_learning_plan(learning_user_id)
    checklist = await db.ensure_study_plan_checklist(learning_user_id)
    homework = list(await db.get_student_homework(learning_user_id, "active") or [])
    pair = None
    get_pair = getattr(db, "get_student_pair_for_student", None)
    if callable(get_pair):
        pair = await get_pair(learning_user_id)
    await message.answer(
        build_study_plan_text(
            user,
            plan,
            checklist.get("lesson"),
            homework,
            list(checklist.get("items") or []),
            pair=pair,
        ),
        reply_markup=make_study_plan_keyboard(plan, list(checklist.get("items") or [])),
    )


@router.message(Command("materials"))
async def command_materials(message: Message, db: Database):
    logger.info(f"Команда /materials от {message.from_user.id}")
    info = load_teacher_info()
    website_url = _get_project_site_url(info)
    user = await db.get_user(message.from_user.id)
    resources: list = []
    if user:
        owner_id = message.from_user.id
        if user.get("role") == "student":
            from handlers.users.callbacks import _get_learning_student_id
            owner_id = await _get_learning_student_id(db, owner_id)
        try:
            resources = list(await db.list_student_resources(owner_id) or [])
        except Exception:
            logger.warning("Failed to load student_resources for /materials", exc_info=True)
            resources = []
    else:
        try:
            resources = list(await db.list_global_resources() or [])
        except Exception:
            resources = []
    await message.answer(
        build_materials_text(resources, website_url=website_url),
        reply_markup=make_materials_keyboard(resources, website_url=website_url),
    )


@router.message(Command("health"))
async def command_health(message: Message, db: Database):
    logger.info(f"Команда /health от {message.from_user.id}")
    if message.from_user.id != config.ADMIN_ID:
        return
    from handlers.users.admin_sections.health import (
        _format_health_text,
        _service_navigation_keyboard,
    )
    students = await db.get_all_students()
    report = load_last_sync_report()
    ops_status = load_ops_status()
    runtime_events = load_recent_runtime_events(limit=30)
    await message.answer(
        _format_health_text(len(students), report, ops_status, runtime_events),
        reply_markup=_service_navigation_keyboard("monitoring"),
    )
