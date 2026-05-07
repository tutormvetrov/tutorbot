import logging
from aiogram import Router, F, html
from aiogram.filters import CommandObject, CommandStart, StateFilter
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
    make_admin_pair_notification_keyboard,
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


def _extract_start_payload(message: Message, command: CommandObject | None = None) -> str:
    if command and command.args:
        return command.args.strip()
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].split("@", 1)[0] == "/start":
        return parts[1].strip()
    return ""


async def _handle_pair_invite_start(message: Message, db: Database, token: str) -> bool:
    if not token:
        await message.answer(
            "⚠️ Ссылка для подключения к паре неполная. Попросите преподавателя прислать её ещё раз."
        )
        return True

    get_invite = getattr(db, "get_student_pair_invite", None)
    accept_invite = getattr(db, "accept_student_pair_invite", None)
    if not callable(get_invite) or not callable(accept_invite):
        await message.answer("⚠️ Подключение второго участника пока недоступно в этой версии бота.")
        return True

    invite = await get_invite(token)
    if not invite:
        await message.answer(
            "⚠️ Ссылка не найдена или уже недоступна. Попросите преподавателя создать новую ссылку."
        )
        return True

    user_id = message.from_user.id
    if user_id == invite["primary_student_id"]:
        await message.answer(
            "ℹ️ Эта ссылка предназначена для второго участника пары. "
            "Основной контакт уже подключён к общему кабинету."
        )
        return True

    if invite["student_id"] and invite["student_id"] != user_id:
        await message.answer(
            "⚠️ Эта ссылка уже использована другим Telegram-профилем. "
            "Попросите преподавателя проверить карточку пары."
        )
        return True

    existing_user = await db.get_user(user_id)
    if existing_user and existing_user.get("role") not in {"student"}:
        await message.answer(
            "⚠️ Этот Telegram-профиль уже зарегистрирован в другой роли. "
            "Попросите преподавателя подключить участника вручную."
        )
        return True

    pair = await accept_invite(
        token,
        user_id,
        message.from_user.full_name,
        message.from_user.username,
    )
    if not pair:
        await message.answer(
            "⚠️ Не удалось подключить вас к паре. Попросите преподавателя создать новую ссылку."
        )
        return True

    if config.ADMIN_ID:
        try:
            telegram_label = f"@{message.from_user.username}" if message.from_user.username else html.quote(message.from_user.full_name)
            pair_id = pair.get("id") if pair else invite["group_id"]
            await message.bot.send_message(
                config.ADMIN_ID,
                f"🔗 <b>Второй участник подключился к паре</b>\n\n"
                f"👥 {html.quote(pair.get('title') or invite['title'])}\n"
                f"👤 {html.quote(invite['member_name'])}\n"
                f"Telegram: {telegram_label}",
                reply_markup=make_admin_pair_notification_keyboard(int(pair_id)),
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу уведомление о подключении к паре %s: %s", user_id, exc)

    home_text, home_keyboard = await get_user_home_payload(db, user_id)
    await message.answer(
        f"✅ <b>Вы подключены к учебной паре.</b>\n\n{home_text}",
        reply_markup=home_keyboard,
    )

    # Pair-onboarding wow: if primary already has a personal goal and the pair
    # has none yet, offer to adopt it as the shared pair goal.
    try:
        primary_id = int(invite["primary_student_id"])
        pair_id = int(pair.get("id") or invite["group_id"])
        primary_user = await db.get_user(primary_id)
        primary_goal = (primary_user.get("goal_text") or "").strip() if primary_user else ""
        existing_pair_goal = (pair.get("shared_goal_text") or "").strip() if isinstance(pair, dict) else ""
        if primary_goal and not existing_pair_goal:
            from keyboards.inline import _btn
            from utils.ui_text import build_pair_invite_goal_inherit_text
            from aiogram.types import InlineKeyboardMarkup
            partner_label = primary_user.get("full_name") or "ваш партнёр"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [_btn("✅ Поддержать", f"pair_goal:inherit:{pair_id}")],
                [_btn("✏️ Поставить свою", "pair_goal:set")],
                [_btn("🙅 Не сейчас", "back_to_menu")],
            ])
            await message.answer(
                build_pair_invite_goal_inherit_text(partner_label, primary_goal),
                reply_markup=kb,
            )
    except Exception:
        logger.warning("Не удалось предложить унаследовать цель пары для %s", user_id, exc_info=True)
    return True


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext, db: Database, command: CommandObject | None = None):
    await state.clear()
    logger.info(f"Команда /start от {message.from_user.id}")
    user_id = message.from_user.id
    payload = _extract_start_payload(message, command)
    if payload.startswith("pair_"):
        if await _handle_pair_invite_start(message, db, payload.removeprefix("pair_")):
            return

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
    total = 6 if role == "student_pair" else 5
    await state.update_data(role=role, reg_total=total)
    await state.set_state(Registration.waiting_for_full_name)
    name_hint = (
        "Введите <b>имя и фамилию основного контактного участника</b>:"
        if role == "student_pair"
        else "Введите ваше <b>имя и фамилию</b>:"
    )
    await callback_query.message.edit_text(
        f"📝 {name_hint}\n\n"
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
    if data.get("role") == "student_pair":
        total = data.get("reg_total", 6)
        level_label = LEVEL_LABELS.get(level, level)
        await state.update_data(level=level)
        await state.set_state(Registration.waiting_for_pair_partner_name)
        await callback_query.message.edit_text(
            f"✅ Уровень: <b>{html.quote(level_label)}</b>\n\n"
            "Как зовут второго участника пары?\n\n"
            "Он может просто присутствовать на уроках: бот всё равно будет вести общий темп, "
            f"баланс и домашние задания на двоих.{_progress(5, total)}",
            reply_markup=cancel_fsm_keyboard,
        )
        await callback_query.answer()
        return

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

    create_initial_journey = getattr(db, "create_initial_journey", None)
    if callable(create_initial_journey):
        try:
            await create_initial_journey(user_id)
        except Exception:
            logger.warning("Не удалось создать journey-события для %s", user_id, exc_info=True)

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

    from handlers.users.callbacks import _build_contacts_text, _get_materials_url
    info = load_teacher_info()
    contacts_text = _build_contacts_text(info, show_address=True)
    booking_url = info.get("contacts", {}).get("booking_url", "")
    website_url = info.get("contacts", {}).get("project_site_url", "")
    materials_url = _get_materials_url(info)

    await callback_query.message.edit_text(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 {safe_full_name}  •  🎂 {data.get('age')} лет\n"
        f"📚 {safe_language}  •  📊 {safe_level_label}\n\n"
        f"{contacts_text}\n\n"
        "📥 Полная инструкция к боту лежит в «👤 Ещё → 📥 Инструкция к боту». "
        "Можно скачать DOCX и читать офлайн.\n\n"
        "Если готовы, ниже есть тест уровня.",
        reply_markup=make_post_registration_keyboard(
            booking_url,
            website_url,
            materials_url,
            include_level_test=True,
        ),
    )
    await callback_query.answer()


@router.message(StateFilter(Registration.waiting_for_pair_partner_name))
async def process_pair_partner_name(message: Message, state: FSMContext, db: Database):
    partner_name = (message.text or "").strip()
    if len(partner_name) < 2:
        await message.answer(
            "⚠️ Введите имя второго участника пары.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    full_name = data["full_name"]
    language = data["language"]
    level = data["level"]
    user_id = message.from_user.id
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=message.from_user.username or "",
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
            message.from_user.username,
            data.get("age"),
            language,
            level,
            is_internal_account,
        )

    pair_id = None
    create_pair = getattr(db, "create_student_pair", None)
    if callable(create_pair):
        pair_id = await create_pair(
            user_id,
            full_name,
            partner_name,
            onboarding_source="self_registration",
        )

    sync_parent_links = getattr(db, "sync_parent_links_for_student", None)
    if callable(sync_parent_links):
        await sync_parent_links(user_id, full_name)

    create_initial_journey = getattr(db, "create_initial_journey", None)
    if callable(create_initial_journey):
        try:
            await create_initial_journey(user_id)
        except Exception:
            logger.warning("Не удалось создать journey-события для пары %s", user_id, exc_info=True)

    await state.clear()
    level_label = LEVEL_LABELS.get(level, level)
    safe_full_name = html.quote(full_name)
    safe_partner_name = html.quote(partner_name)
    safe_language = html.quote(language)
    safe_level_label = html.quote(level_label)

    if config.ADMIN_ID:
        try:
            next_step = (
                "Нажмите кнопку ниже, чтобы создать ссылку для второго участника."
                if pair_id
                else "Откройте раздел «Пары», чтобы создать ссылку для второго участника."
            )
            await message.bot.send_message(
                config.ADMIN_ID,
                f"🎉 <b>Новая учебная пара!</b>\n\n"
                f"👥 {safe_full_name} + {safe_partner_name}\n"
                f"🎂 Возраст основного контакта: {data.get('age')} лет\n"
                f"📚 Язык: {safe_language}  •  📊 Уровень: {safe_level_label}\n"
                f"🧭 Основной контакт: {safe_full_name}\n\n"
                f"{next_step}",
                reply_markup=make_admin_pair_notification_keyboard(int(pair_id)) if pair_id else None,
            )
        except Exception as exc:
            logger.warning("Не удалось отправить админу уведомление о новой паре %s: %s", user_id, exc)

    from handlers.users.callbacks import _build_contacts_text, _get_materials_url
    info = load_teacher_info()
    contacts_text = _build_contacts_text(info, show_address=True)
    booking_url = info.get("contacts", {}).get("booking_url", "")
    website_url = info.get("contacts", {}).get("project_site_url", "")
    materials_url = _get_materials_url(info)

    await message.answer(
        f"✅ <b>Регистрация пары завершена!</b>\n\n"
        f"👥 {safe_full_name} + {safe_partner_name}\n"
        f"📚 {safe_language}  •  📊 {safe_level_label}\n\n"
        "Бот будет вести вас как одну учебную пару: общий баланс, один темп и одно ДЗ на двоих."
        "\n\n"
        f"{contacts_text}\n\n"
        "Если готовы, ниже есть тест уровня для стартовой диагностики.",
        reply_markup=make_post_registration_keyboard(
            booking_url,
            website_url,
            materials_url,
            include_level_test=True,
        ),
    )


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

    add_inbox_event = getattr(db, "add_inbox_event", None)
    if callable(add_inbox_event):
        try:
            await add_inbox_event("first_contact", {
                "telegram_id": message.from_user.id,
                "full_name": full_name,
                "context": "general",
                "child_name": student_name,
                "link_status": "linked" if linked_student else "waiting_link",
                "message_preview": f"Регистрация родителя: {full_name}, ребёнок {student_name}",
            })
        except Exception:
            logger.warning("Не удалось записать first_contact в admin_inbox", exc_info=True)

    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 Вы: {html.quote(full_name)}\n"
        f"👧 Ребёнок: {html.quote(student_name)}, {student_age} лет.\n\n"
        f"{'✅ Связь с учеником найдена.' if linked_student else '⏳ Связь появится автоматически, когда имя совпадёт с активным профилем ученика.'}\n\n"
        "📥 Памятка для родителя — «👤 Ещё → 📥 Инструкция к боту».",
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
