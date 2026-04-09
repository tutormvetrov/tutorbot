import logging
from aiogram import Router, F, html
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from data import config
from data.config import load_teacher_info, is_internal_test_account
from handlers.users.screens import get_user_home_payload
from keyboards.inline import (
    admin_keyboard,
    role_keyboard,
    parent_main_keyboard,
    level_keyboard,
    cancel_fsm_keyboard,
    make_post_registration_keyboard,
)
from states.registration import Registration
from utils.db_api.postgresql import Database
from utils.google_calendar import load_last_sync_report
from utils.observability import load_ops_status
from utils.text_utils import normalize_language, parse_age
from utils.ui_text import build_admin_dashboard_text

router = Router()
logger = logging.getLogger(__name__)


def _progress(step: int, total: int) -> str:
    filled = "▓" * step
    empty = "░" * (total - step)
    return f"\n\n<i>Шаг {step} из {total}: {filled}{empty}</i>"


async def _register_admin(message: Message, db: Database):
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role)
            VALUES ($1, $2, $3, 'teacher_admin')
            ON CONFLICT (telegram_id) DO UPDATE SET role = 'teacher_admin'
            """,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
        )
    snapshot = await db.get_admin_dashboard_snapshot()
    ops_status = load_ops_status()
    sync_report = load_last_sync_report()
    await message.answer(
        build_admin_dashboard_text(snapshot, ops_status, sync_report),
        reply_markup=admin_keyboard,
    )


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    logger.info(f"Команда /start от {message.from_user.id}")
    user_id = message.from_user.id

    if user_id == config.ADMIN_ID:
        await _register_admin(message, db)
        return

    user = await db.get_user(user_id)

    if not user:
        await state.set_state(Registration.waiting_for_role)
        await message.answer(
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Пожалуйста, выберите вашу роль:",
            reply_markup=role_keyboard,
        )
    else:
        text, keyboard = await get_user_home_payload(db, user_id)
        await message.answer(text, reply_markup=keyboard)


# ─── Role selected ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("role:"))
async def process_role_choice(callback_query: CallbackQuery, state: FSMContext):
    role = callback_query.data.split(":")[1]
    total = 5
    await state.update_data(role=role, reg_total=total)
    await state.set_state(Registration.waiting_for_full_name)
    await callback_query.message.edit_text(
        "📝 Введите ваше <b>имя и фамилию</b>:\n\n"
        f"Например: <code>Иван Петров</code>{_progress(1, total)}",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


# ─── Name entered ─────────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_full_name))
async def process_full_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(
            "⚠️ Введите имя и фамилию (минимум 2 символа).",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    total = data.get("reg_total", 5)
    await state.update_data(full_name=name)
    await state.set_state(Registration.waiting_for_age)
    safe_name = html.quote(name)
    await message.answer(
        f"✅ Имя сохранено: <b>{safe_name}</b>\n\n"
        f"Сколько вам лет?\n\n"
        f"Например: <code>16</code> или <code>шестнадцать</code>{_progress(2, total)}",
        reply_markup=cancel_fsm_keyboard,
    )


# ─── Age entered ──────────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_age))
async def process_age(message: Message, state: FSMContext):
    age = parse_age((message.text or "").strip())
    if age is None:
        await message.answer(
            "⚠️ Не удалось распознать возраст. Введите число или словами:\n"
            "<code>16</code> или <code>шестнадцать</code>",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    role = data.get("role")
    total = data.get("reg_total", 5)
    await state.update_data(age=age)

    if role == "parent":
        await state.set_state(Registration.waiting_for_child_name)
        await message.answer(
            f"✅ Возраст: <b>{age} лет</b>\n\n"
            "Как зовут ребёнка?\n\n"
            f"Например: <code>Анна Петрова</code>{_progress(3, total)}",
            reply_markup=cancel_fsm_keyboard,
        )
    else:
        await state.set_state(Registration.waiting_for_language)
        await message.answer(
            f"✅ Возраст: <b>{age} лет</b>\n\n"
            "Какой язык вы хотите изучать?\n\n"
            f"Например: <code>английский</code>, <code>French</code>{_progress(3, total)}",
            reply_markup=cancel_fsm_keyboard,
        )


# ─── Language entered ─────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_language))
async def process_language(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "⚠️ Введите название языка.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    language, is_known = normalize_language(raw)
    data = await state.get_data()
    total = data.get("reg_total", 5)
    await state.update_data(language=language)
    await state.set_state(Registration.waiting_for_level)

    if is_known:
        lang_line = f"✅ Язык: <b>{language}</b>"
    else:
        lang_line = (
            f"⚠️ Язык сохранён как «<b>{language}</b>».\n"
            "Если это опечатка — введите язык снова.\n"
            "Иначе выберите уровень ниже:"
        )
    await message.answer(
        f"{lang_line}{_progress(4, total)}\n\n"
        "Выберите ваш текущий уровень:",
        reply_markup=level_keyboard,
    )


# ─── Level selected ───────────────────────────────────────────────────────────

LEVEL_LABELS = {
    "A1": "A1 — Начинающий",
    "A2": "A2 — Элементарный",
    "B1": "B1 — Средний",
    "B2": "B2 — Выше среднего",
    "C1": "C1 — Продвинутый",
    "C2": "C2 — Мастерство",
    "unknown": "Не знаю",
}


@router.callback_query(F.data.startswith("level:"), StateFilter(Registration.waiting_for_level))
async def process_level(callback_query: CallbackQuery, state: FSMContext, db: Database):
    level = callback_query.data.split(":", 1)[1]
    data = await state.get_data()
    full_name = data["full_name"]
    language = data["language"]
    user_id = callback_query.from_user.id
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=callback_query.from_user.username or "",
        telegram_id=user_id,
    )

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, age, language, level, is_internal_account)
            VALUES ($1, $2, $3, 'student', $4, $5, $6, $7)
            ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                age = EXCLUDED.age,
                language = EXCLUDED.language,
                level = EXCLUDED.level,
                is_internal_account = EXCLUDED.is_internal_account,
                is_active = true
            """,
            user_id,
            full_name,
            callback_query.from_user.username,
            data.get("age"),
            language,
            level,
            is_internal_account,
        )
    sync_parent_links = getattr(db, "sync_parent_links_for_student", None)
    if callable(sync_parent_links):
        await sync_parent_links(user_id, full_name)

    await state.clear()
    level_label = LEVEL_LABELS.get(level, level)
    safe_full_name = html.quote(full_name)
    safe_language = html.quote(language)
    safe_level_label = html.quote(level_label)

    if config.ADMIN_ID:
        try:
            await callback_query.bot.send_message(
                config.ADMIN_ID,
                f"🎉 <b>Новый ученик!</b>\n\n"
                f"👤 {safe_full_name}\n"
                f"🎂 Возраст: {data.get('age')} лет\n"
                f"📚 Язык: {safe_language}  •  📊 Уровень: {safe_level_label}",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу уведомление о новом ученике %s: %s", user_id, exc)

    from handlers.users.callbacks import _build_contacts_text
    info = load_teacher_info()
    contacts_text = _build_contacts_text(info, show_address=True)
    booking_url = info.get("contacts", {}).get("booking_url", "")
    website_url = info.get("contacts", {}).get("project_site_url", "")

    await callback_query.message.edit_text(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 {safe_full_name}  •  🎂 {data.get('age')} лет\n"
        f"📚 {safe_language}  •  📊 {safe_level_label}\n\n"
        f"{contacts_text}\n\n"
        "Если готовы, ниже есть тест уровня.",
        reply_markup=make_post_registration_keyboard(
            booking_url,
            website_url,
            include_level_test=True,
        ),
    )
    await callback_query.answer()


# ─── Parent: child info ────────────────────────────────────────────────────────


async def _finish_parent_registration(
    message: Message,
    state: FSMContext,
    db: Database,
    student_name: str,
    student_age: int,
):
    data = await state.get_data()
    full_name = data["full_name"]
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=message.from_user.username or "",
        telegram_id=message.from_user.id,
    )

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, age, is_internal_account)
            VALUES ($1, $2, $3, 'parent', $4, $5)
            ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                age = EXCLUDED.age,
                is_internal_account = EXCLUDED.is_internal_account,
                is_active = true
            """,
            message.from_user.id,
            full_name,
            message.from_user.username,
            data.get("age"),
            is_internal_account,
        )

    find_active_student = getattr(db, "find_active_student_by_name", None)
    linked_student = await find_active_student(student_name) if callable(find_active_student) else None
    upsert_parent_link = getattr(db, "upsert_parent_student_link", None)
    if callable(upsert_parent_link):
        await upsert_parent_link(
            parent_id=message.from_user.id,
            student_info=f"{student_name} ({student_age})",
            student_id=linked_student["telegram_id"] if linked_student else None,
        )

    await state.clear()
    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 Вы: {html.quote(full_name)}\n"
        f"👧 Ребёнок: {html.quote(student_name)}, {student_age} лет.\n\n"
        f"{'✅ Связь с учеником найдена.' if linked_student else '⏳ Связь появится автоматически, когда имя совпадёт с активным профилем ученика.'}",
        reply_markup=parent_main_keyboard,
    )


@router.message(StateFilter(Registration.waiting_for_child_name))
async def process_child_name(message: Message, state: FSMContext):
    child_name = (message.text or "").strip()
    if len(child_name) < 2:
        await message.answer(
            "⚠️ Введите имя и фамилию ребёнка.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    total = (await state.get_data()).get("reg_total", 5)
    await state.update_data(child_name=child_name)
    await state.set_state(Registration.waiting_for_child_age)
    await message.answer(
        f"✅ Ребёнок: <b>{html.quote(child_name)}</b>\n\n"
        f"Сколько ему лет?\n\n"
        f"Например: <code>14</code>{_progress(4, total)}",
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(Registration.waiting_for_child_age))
async def process_child_age(message: Message, state: FSMContext, db: Database):
    child_age = parse_age((message.text or "").strip())
    if child_age is None:
        await message.answer(
            "⚠️ Не удалось распознать возраст ребёнка. Введите число или возраст словами.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    child_name = (await state.get_data()).get("child_name", "").strip()
    if not child_name:
        await state.set_state(Registration.waiting_for_child_name)
        await message.answer(
            "⚠️ Сначала укажите имя ребёнка.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await _finish_parent_registration(message, state, db, child_name, child_age)


@router.message(StateFilter(Registration.waiting_for_student_info))
async def process_student_info(message: Message, state: FSMContext, db: Database):
    parts = (message.text or "").split(",", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        await message.answer(
            "⚠️ Не удалось распознать формат. Введите данные так:\n"
            "<b>Анна Петрова, 14</b>",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    student_name = parts[0].strip()
    student_age = parse_age(parts[1].strip())
    if student_age is None:
        await message.answer(
            "⚠️ Не удалось распознать возраст ребёнка. Введите данные так:\n"
            "<b>Анна Петрова, 14</b>",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await _finish_parent_registration(message, state, db, student_name, student_age)
