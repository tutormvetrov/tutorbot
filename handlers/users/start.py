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
    engagement_mode_keyboard,
    student_type_keyboard,
    make_admin_pair_notification_keyboard,
    make_parent_home_keyboard,
    make_post_registration_keyboard,
)
from states.registration import Registration
from utils.db_api.postgresql import Database
from utils.google_calendar import load_last_sync_report
from utils.observability import load_ops_status
from utils.text_utils import normalize_language, parse_age, parse_pair_name_input
from utils.ui_text import (
    build_admin_dashboard_text,
    build_engagement_mode_intro_text,
    build_registration_done_text,
    build_registration_step_text,
    build_parent_home_text,
)

router = Router()
logger = logging.getLogger(__name__)


def _progress(step: int, total: int) -> str:
    filled = "▓" * step
    empty = "░" * (total - step)
    return f"\n\n<i>Шаг {step} из {total}: {filled}{empty}</i>"


def _registration_already(data: dict, *keys: str) -> list[str]:
    labels = {
        "full_name": "ФИО: {value}",
        "age": "Возраст: {value}",
        "student_type": "Тип: {value}",
        "language": "Язык: {value}",
        "level": "Уровень: {value}",
        "child_name": "Ребёнок: {value}",
        "child_age": "Возраст ребёнка: {value}",
    }
    type_labels = {"adult": "взрослый", "schoolchild": "школьник"}
    result = []
    for key in keys:
        value = data.get(key)
        if value is None or value == "":
            continue
        if key == "student_type":
            value = type_labels.get(str(value), str(value))
        if key == "level":
            value = LEVEL_LABELS.get(str(value), str(value))
        result.append(labels.get(key, "{value}").format(value=value))
    return result


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
            "Сейчас быстро настроим профиль. Обычно это занимает пару минут.\n"
            "Выберите вашу роль:",
            reply_markup=role_keyboard,
        )
    else:
        text, keyboard = await get_user_home_payload(db, user_id)
        await message.answer(text, reply_markup=keyboard)


# ─── Role selected ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("role:"))
async def process_role_choice(callback_query: CallbackQuery, state: FSMContext):
    role = callback_query.data.split(":")[1]
    total = 7 if role == "student_pair" else 6
    await state.update_data(role=role, reg_total=total)
    await state.set_state(Registration.waiting_for_full_name)
    name_hint = (
        "Введите <b>имя и фамилию основного контактного участника</b>:"
        if role == "student_pair"
        else "Введите ваше <b>имя и фамилию</b>:"
    )
    example = (
        "<code>Даниил Безруков</code>"
        if role == "student_pair"
        else "<code>Иван Петров</code>"
    )
    await callback_query.message.edit_text(
        build_registration_step_text(
            1,
            total,
            f"📝 {name_hint}",
            example=example,
        ),
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
    total = data.get("reg_total", 6)
    await state.update_data(full_name=name)
    await state.set_state(Registration.waiting_for_age)
    safe_name = html.quote(name)
    await message.answer(
        build_registration_step_text(
            2,
            total,
            "Сколько вам лет?",
            already=[f"ФИО: {name}"],
            example="<code>16</code> или <code>шестнадцать</code>",
        ),
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
    total = data.get("reg_total", 6)
    await state.update_data(age=age)

    if role == "parent":
        await state.set_state(Registration.waiting_for_child_name)
        await message.answer(
            build_registration_step_text(
                3,
                total,
                "Как зовут ребёнка?",
                already=_registration_already(data, "full_name") + [f"Возраст: {age}"],
                example="<code>Анна Петрова</code>",
            ),
            reply_markup=cancel_fsm_keyboard,
        )
    else:
        await state.set_state(Registration.waiting_for_student_type)
        await message.answer(
            build_registration_step_text(
                3,
                total,
                "Вы взрослый ученик или школьник?",
                already=_registration_already(data, "full_name") + [f"Возраст: {age}"],
                note="Выберите вариант кнопкой ниже.",
            ),
            reply_markup=student_type_keyboard,
        )


# ─── Student type selected ───────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("student_type:"))
async def process_student_type(callback_query: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != Registration.waiting_for_student_type.state:
        logger.info(
            "stale student_type callback: user=%s state=%s data=%s",
            callback_query.from_user.id, current_state, callback_query.data,
        )
        await callback_query.answer()
        return
    chosen = callback_query.data.split(":", 1)[1]
    data = await state.get_data()
    total = data.get("reg_total", 6)
    if chosen == "schoolchild":
        await state.update_data(student_type="schoolchild", speech_style="schoolchild")
        label = "🎒 Школьник"
    else:
        await state.update_data(student_type="adult", speech_style="formal")
        label = "🎓 Взрослый"
    await state.set_state(Registration.waiting_for_language)
    await callback_query.message.edit_text(
        build_registration_step_text(
            4,
            total,
            "Какой язык вы хотите изучать?",
            already=_registration_already(data, "full_name", "age") + [f"Тип: {label}"],
            example="<code>английский</code>, <code>French</code>",
        ),
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


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
    total = data.get("reg_total", 6)
    await state.update_data(language=language)
    await state.set_state(Registration.waiting_for_level)

    question = "Выберите ваш текущий уровень:"
    if not is_known:
        question = f"Язык сохранён как «<b>{html.quote(language)}</b>». Если это опечатка, отправьте язык ещё раз. Иначе выберите уровень:"
    await message.answer(
        build_registration_step_text(
            5,
            total,
            question,
            already=_registration_already(data, "full_name", "age", "student_type") + [f"Язык: {language}"],
            note="Выберите вариант кнопкой ниже.",
        ),
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
            build_registration_step_text(
                6,
                total,
                "Как зовут второго участника пары?",
                already=_registration_already(data, "full_name", "age", "student_type", "language") + [f"Уровень: {level_label}"],
                example="<code>Полина</code> или <code>Безруковы Даниил и Полина</code>",
            ),
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

    student_type = data.get("student_type", "adult")
    reg_speech_style = data.get("speech_style", "formal")
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, age, language, level,
                               is_internal_account, student_type, speech_style)
            VALUES ($1, $2, $3, 'student', $4, $5, $6, $7, $8, $9)
            ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                age = EXCLUDED.age,
                language = EXCLUDED.language,
                level = EXCLUDED.level,
                is_internal_account = EXCLUDED.is_internal_account,
                student_type = EXCLUDED.student_type,
                speech_style = EXCLUDED.speech_style,
                is_active = true
            """,
            user_id,
            full_name,
            callback_query.from_user.username,
            data.get("age"),
            language,
            level,
            is_internal_account,
            student_type,
            reg_speech_style,
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
        build_registration_done_text(
            "Регистрация завершена",
            [
                f"👤 {safe_full_name}",
                f"🎂 {data.get('age')} лет",
                f"📚 {safe_language}",
                f"📊 {safe_level_label}",
            ],
            contacts_text,
            next_hint="Если готовы, ниже есть тест уровня и инструкция к боту.",
        ),
        reply_markup=make_post_registration_keyboard(
            booking_url,
            website_url,
            materials_url,
            include_level_test=True,
            guide_callback="guide:menu:student",
        ),
    )
    await callback_query.answer()

    try:
        rules = list(await db.get_work_rules() or [])
        if rules:
            from utils.ui_text import build_onboarding_rules_text
            from keyboards.inline import work_rules_onboarding_keyboard
            rules_text = build_onboarding_rules_text(rules)
            if rules_text:
                await callback_query.message.answer(
                    rules_text,
                    reply_markup=work_rules_onboarding_keyboard,
                )
    except Exception:
        logger.warning("Не удалось показать правила при регистрации %s", user_id, exc_info=True)


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
    parsed_pair = parse_pair_name_input(full_name, partner_name)
    full_name = parsed_pair["primary_name"] or full_name
    partner_name = parsed_pair["partner_name"] or partner_name
    language = data["language"]
    level = data["level"]
    user_id = message.from_user.id
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=message.from_user.username or "",
        telegram_id=user_id,
    )

    student_type = data.get("student_type", "adult")
    reg_speech_style = data.get("speech_style", "formal")
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, age, language, level,
                               is_internal_account, student_type, speech_style)
            VALUES ($1, $2, $3, 'student', $4, $5, $6, $7, $8, $9)
            ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                age = EXCLUDED.age,
                language = EXCLUDED.language,
                level = EXCLUDED.level,
                is_internal_account = EXCLUDED.is_internal_account,
                student_type = EXCLUDED.student_type,
                speech_style = EXCLUDED.speech_style,
                is_active = true
            """,
            user_id,
            full_name,
            message.from_user.username,
            data.get("age"),
            language,
            level,
            is_internal_account,
            student_type,
            reg_speech_style,
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
        build_registration_done_text(
            "Регистрация пары завершена",
            [
                f"👥 {safe_full_name} + {safe_partner_name}",
                f"📚 {safe_language}",
                f"📊 {safe_level_label}",
                "Общий баланс, один темп и одно ДЗ на двоих.",
            ],
            contacts_text,
            next_hint="Если готовы, ниже есть тест уровня и инструкция к боту.",
        ),
        reply_markup=make_post_registration_keyboard(
            booking_url,
            website_url,
            materials_url,
            include_level_test=True,
            guide_callback="guide:menu:student",
        ),
    )

    try:
        rules = list(await db.get_work_rules() or [])
        if rules:
            from utils.ui_text import build_onboarding_rules_text
            from keyboards.inline import work_rules_onboarding_keyboard
            rules_text = build_onboarding_rules_text(rules)
            if rules_text:
                await message.answer(
                    rules_text,
                    reply_markup=work_rules_onboarding_keyboard,
                )
    except Exception:
        logger.warning("Не удалось показать правила при регистрации пары %s", user_id, exc_info=True)


# ─── Parent: child info ────────────────────────────────────────────────────────


async def _finish_parent_registration(
    message: Message,
    state: FSMContext,
    db: Database,
    student_name: str,
    student_age: int,
    engagement_mode: str = "active",
):
    data = await state.get_data()
    full_name = data["full_name"]
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=message.from_user.username or "",
        telegram_id=message.from_user.id,
    )
    normalized_mode = engagement_mode if engagement_mode in {"active", "trust"} else "active"

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, age, is_internal_account, engagement_mode)
            VALUES ($1, $2, $3, 'parent', $4, $5, $6)
            ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                age = EXCLUDED.age,
                is_internal_account = EXCLUDED.is_internal_account,
                engagement_mode = EXCLUDED.engagement_mode,
                is_active = true
            """,
            message.from_user.id,
            full_name,
            message.from_user.username,
            data.get("age"),
            is_internal_account,
            normalized_mode,
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
                "engagement_mode": normalized_mode,
                "message_preview": f"Регистрация родителя: {full_name}, ребёнок {student_name} ({normalized_mode})",
            })
        except Exception:
            logger.warning("Не удалось записать first_contact в admin_inbox", exc_info=True)

    children = []
    overview_fn = getattr(db, "get_parent_children_overview", None)
    if callable(overview_fn):
        try:
            children = list(await overview_fn(message.from_user.id) or [])
        except Exception:
            logger.warning("Не удалось получить overview детей после регистрации", exc_info=True)
            children = []

    mode_line = (
        "🎯 Режим: <b>активное наблюдение</b>"
        if normalized_mode == "active"
        else "🌿 Режим: <b>доверие преподавателю</b>"
    )
    link_line = (
        "✅ Связь с учеником найдена."
        if linked_student
        else "⏳ Связь появится автоматически, когда имя совпадёт с активным профилем ученика."
    )
    from handlers.users.callbacks import _build_contacts_text
    header = (
        build_registration_done_text(
            "Регистрация завершена",
            [
                f"👤 Вы: {html.quote(full_name)}",
                f"👧 Ребёнок: {html.quote(student_name)}, {student_age} лет",
                mode_line,
                link_line,
            ],
            _build_contacts_text(load_teacher_info(), show_address=True),
            next_hint="Памятка для родителя доступна кнопкой ниже.",
        )
    )

    await message.answer(
        header,
        reply_markup=make_post_registration_keyboard(
            guide_callback="guide:send:parent",
            include_parent_home=True,
        ),
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

    total = (await state.get_data()).get("reg_total", 6)
    data = await state.get_data()
    await state.update_data(child_name=child_name)
    await state.set_state(Registration.waiting_for_child_age)
    await message.answer(
        build_registration_step_text(
            4,
            total,
            "Сколько лет ребёнку?",
            already=_registration_already(data, "full_name", "age") + [f"Ребёнок: {child_name}"],
            example="<code>14</code>",
        ),
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(Registration.waiting_for_child_age))
async def process_child_age(message: Message, state: FSMContext):
    child_age = parse_age((message.text or "").strip())
    if child_age is None:
        await message.answer(
            "⚠️ Не удалось распознать возраст ребёнка. Введите число или возраст словами.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    child_name = (data.get("child_name") or "").strip()
    if not child_name:
        await state.set_state(Registration.waiting_for_child_name)
        await message.answer(
            "⚠️ Сначала укажите имя ребёнка.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    total = data.get("reg_total", 6)
    await state.update_data(child_age=child_age)
    await state.set_state(Registration.waiting_for_engagement_mode)
    await message.answer(
        build_registration_step_text(
            5,
            total,
            "Как показывать кабинет родителя?\n\n"
            "🎯 Быть в курсе: расписание, ДЗ, план и оплаты.\n"
            "🌿 Доверие: расписание и оплаты.",
            already=_registration_already(data, "full_name", "age", "child_name") + [f"Возраст ребёнка: {child_age}"],
            note="Выберите вариант кнопкой ниже.",
        ),
        reply_markup=engagement_mode_keyboard,
    )


@router.callback_query(
    F.data.startswith("engagement:"),
    StateFilter(Registration.waiting_for_engagement_mode),
)
async def process_engagement_mode_choice(callback_query: CallbackQuery, state: FSMContext, db: Database):
    mode = callback_query.data.split(":", 1)[1]
    if mode not in {"active", "trust"}:
        await callback_query.answer("Выберите один из двух вариантов.", show_alert=True)
        return

    data = await state.get_data()
    child_name = (data.get("child_name") or "").strip()
    child_age = data.get("child_age")
    if not child_name or child_age is None:
        await state.set_state(Registration.waiting_for_child_name)
        await callback_query.message.answer(
            "⚠️ Что-то пошло не так с данными ребёнка. Введите имя ребёнка ещё раз.",
            reply_markup=cancel_fsm_keyboard,
        )
        await callback_query.answer()
        return

    try:
        await callback_query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _finish_parent_registration(
        callback_query.message,
        state,
        db,
        child_name,
        int(child_age),
        engagement_mode=mode,
    )
    await callback_query.answer("Готово.")


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
