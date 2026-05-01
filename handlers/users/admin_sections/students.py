from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from data.config import is_internal_test_account
from handlers.users.admin_sections.common import (
    MessageEditor,
    extract_broadcast_payload,
    get_message_origin,
    is_admin,
    message_to_html,
    q,
    restore_admin_view,
)
from keyboards.inline import (
    back_to_admin_keyboard,
    cancel_fsm_keyboard,
    make_back_button_keyboard,
    make_admin_lesson_formats_keyboard,
    make_admin_pair_card_keyboard,
    make_admin_pair_primary_keyboard,
    make_admin_pairs_list_keyboard,
    make_admin_speech_styles_keyboard,
    make_admin_student_actions_keyboard,
    make_admin_student_card_keyboard,
    make_admin_student_danger_keyboard,
    make_admin_student_danger_confirm_keyboard,
    make_admin_student_danger_review_keyboard,
    make_admin_student_settings_keyboard,
    make_admin_students_list_keyboard,
    make_deactivate_confirm_keyboard,
    make_deactivate_review_keyboard,
    make_delete_confirm_keyboard,
    make_delete_review_keyboard,
    make_student_select_keyboard,
    make_teacher_reply_keyboard,
)
from states.registration import (
    AdminAddStudent,
    AdminCreatePair,
    AdminLessonFollowup,
    AdminManageStudent,
    AdminStudentsDirectory,
    AdminWriteToStudent,
)
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_LESSON_FORMATS_EMPTY_TEXT,
    ADMIN_NO_ACTIVE_STUDENTS_TEXT,
    ADMIN_NO_REGISTERED_STUDENTS_TEXT,
    ADMIN_SPEECH_STYLES_EMPTY_TEXT,
    ADMIN_STUDENTS_EMPTY_TEXT,
    build_action_result_text,
    build_admin_pair_card_text,
    build_admin_pairs_page_text,
    build_admin_students_page_text,
    build_admin_student_card_text,
    format_datetime,
    lesson_format_label,
)
from utils.speech import normalize_speech_style, speech_style_label

router = Router()

ADMIN_STUDENTS_PAGE_SIZE = 5
ADMIN_STUDENT_FILTER_LABELS = {
    "all": "Все",
    "attention": "Нужно внимание",
    "zero_balance": "0 на балансе",
    "no_upcoming": "Без урока",
}
ADMIN_STUDENT_SORT_LABELS = {
    "name": "По имени",
    "balance": "По балансу",
    "lesson": "По ближайшему уроку",
}


def _build_student_summary_line(student, index: int) -> str:
    language = q(student.get("language") or "—")
    level = q(student.get("level") or "—")
    full_name = q(student["full_name"])
    balance = student.get("lesson_balance") or 0
    balance_str = f"{balance} уроков" if balance else "⚠️ 0 уроков"
    format_str = lesson_format_label(student.get("lesson_format"))
    next_lesson = student.get("next_lesson_date")
    if next_lesson:
        lesson_line = f"📅 Следующий урок: {next_lesson.strftime('%d.%m %H:%M')}"
    else:
        lesson_line = "📅 Нет запланированных уроков"
    return (
        f"<b>{index}. {full_name}</b>  |  {language} {level}  |  {balance_str}  |  {format_str}\n"
        f"{lesson_line}"
    )


def _normalize_admin_students_filter(value: str | None) -> str:
    if value in ADMIN_STUDENT_FILTER_LABELS:
        return value
    return "all"


def _normalize_admin_students_query(value: str | None) -> str:
    return " ".join((value or "").strip().split())


async def _get_admin_students_view_state(state: FSMContext | None) -> tuple[str, str, str]:
    if state is None:
        return "all", "", "name"
    data = await state.get_data()
    return (
        _normalize_admin_students_filter(data.get("admin_students_filter")),
        _normalize_admin_students_query(data.get("admin_students_query")),
        _normalize_admin_students_sort(data.get("admin_students_sort")),
    )


def _normalize_admin_students_sort(value: str | None) -> str:
    if value in ADMIN_STUDENT_SORT_LABELS:
        return value
    return "name"


def _student_matches_admin_filter(student, filter_key: str, query: str) -> bool:
    balance = int(student.get("lesson_balance") or 0)
    has_upcoming = bool(student.get("next_lesson_date"))

    if filter_key == "attention" and balance > 0 and has_upcoming:
        return False
    if filter_key == "zero_balance" and balance != 0:
        return False
    if filter_key == "no_upcoming" and has_upcoming:
        return False

    if query:
        haystack = " ".join([
            str(student.get("telegram_id") or ""),
            student.get("full_name") or "",
            student.get("language") or "",
            student.get("level") or "",
        ]).lower()
        for token in query.lower().split():
            if token not in haystack:
                return False

    return True


def _filter_admin_students(students: list, filter_key: str, query: str) -> list:
    return [
        student
        for student in students
        if _student_matches_admin_filter(student, filter_key, query)
    ]


def _sort_admin_students(students: list, sort_key: str) -> list:
    items = list(students or [])
    if sort_key == "balance":
        return sorted(
            items,
            key=lambda student: (
                int(student.get("lesson_balance") or 0),
                not bool(student.get("next_lesson_date")),
                student.get("next_lesson_date") or 0,
                (student.get("full_name") or "").casefold(),
            ),
        )
    if sort_key == "lesson":
        return sorted(
            items,
            key=lambda student: (
                not bool(student.get("next_lesson_date")),
                student.get("next_lesson_date") or 0,
                int(student.get("lesson_balance") or 0),
                (student.get("full_name") or "").casefold(),
            ),
        )
    return sorted(
        items,
        key=lambda student: (
            (student.get("full_name") or "").casefold(),
            int(student.get("lesson_balance") or 0),
        ),
    )


async def _render_admin_students_page(
    message: types.Message,
    db: Database,
    page: int = 0,
    state: FSMContext | None = None,
):
    students = list(await db.get_students_overview() or [])

    if not students:
        await message.edit_text(ADMIN_STUDENTS_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
        return

    filter_key, query, sort_key = await _get_admin_students_view_state(state)
    filtered_students = _sort_admin_students(
        _filter_admin_students(students, filter_key, query),
        sort_key,
    )
    total_pages = max(1, (len(filtered_students) + ADMIN_STUDENTS_PAGE_SIZE - 1) // ADMIN_STUDENTS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    if state is not None:
        await state.set_state(AdminStudentsDirectory.browsing)
        await state.update_data(
            admin_students_filter=filter_key,
            admin_students_query=query,
            admin_students_sort=sort_key,
            admin_students_page=page,
        )

    await message.edit_text(
        build_admin_students_page_text(
            filtered_students,
            page,
            ADMIN_STUDENTS_PAGE_SIZE,
            filter_label=ADMIN_STUDENT_FILTER_LABELS.get(filter_key, ADMIN_STUDENT_FILTER_LABELS["all"]),
            query=query,
            sort_label=ADMIN_STUDENT_SORT_LABELS.get(sort_key, ADMIN_STUDENT_SORT_LABELS["name"]),
            total_count=len(students),
        ),
        reply_markup=make_admin_students_list_keyboard(
            filtered_students,
            page=page,
            page_size=ADMIN_STUDENTS_PAGE_SIZE,
            active_filter=filter_key,
            active_sort=sort_key,
            has_query=bool(query),
        ),
    )


async def _render_admin_student_card(message: types.Message, db: Database, student_id: int, page: int):
    student = await db.get_user(student_id)

    if not student or student["role"] != "student" or student["is_active"] is False:
        await message.edit_text(
            "⚠️ Ученик не найден или уже деактивирован.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    balance = await db.get_student_lesson_balance(student_id)
    next_lessons = await db.get_active_lessons(student_id)
    next_lesson = next_lessons[0]["lesson_date"] if next_lessons and next_lessons[0].get("lesson_date") else None
    pair = None
    get_pair = getattr(db, "get_student_pair_for_student", None)
    if callable(get_pair):
        pair = await get_pair(student_id)

    await message.edit_text(
        build_admin_student_card_text(student, balance, next_lesson, pair=pair),
        reply_markup=make_admin_student_card_keyboard(student_id, page),
    )


async def _render_admin_student_actions(message: types.Message, db: Database, student_id: int, page: int):
    student = await db.get_user(student_id)
    if not student or student["role"] != "student" or student["is_active"] is False:
        await message.edit_text("⚠️ Ученик не найден или уже деактивирован.", reply_markup=back_to_admin_keyboard)
        return
    await message.edit_text(
        "\n".join([
            f"⚡ <b>Действия: {q(student['full_name'])}</b>",
            "",
            "Здесь собраны быстрые рабочие действия по ученику.",
        ]),
        reply_markup=make_admin_student_actions_keyboard(student_id, page),
    )


async def _render_admin_student_settings(message: types.Message, db: Database, student_id: int, page: int):
    student = await db.get_user(student_id)
    if not student or student["role"] != "student" or student["is_active"] is False:
        await message.edit_text("⚠️ Ученик не найден или уже деактивирован.", reply_markup=back_to_admin_keyboard)
        return
    await message.edit_text(
        "\n".join([
            f"⚙️ <b>Настройки: {q(student['full_name'])}</b>",
            "",
            "Здесь можно менять формат занятий, обращение и длительность урока.",
        ]),
        reply_markup=make_admin_student_settings_keyboard(
            student_id,
            page,
            lesson_format=student.get("lesson_format") or "online",
            speech_style=student.get("speech_style") or "formal",
            lesson_duration_minutes=int(student.get("lesson_duration_minutes") or 90),
        ),
    )


async def _render_admin_student_danger(message: types.Message, db: Database, student_id: int, page: int):
    student = await db.get_user(student_id)
    if not student or student["role"] != "student" or student["is_active"] is False:
        await message.edit_text("⚠️ Ученик не найден или уже деактивирован.", reply_markup=back_to_admin_keyboard)
        return
    await message.edit_text(
        "\n".join([
            f"🛡 <b>Опасные действия: {q(student['full_name'])}</b>",
            "",
            "Эти действия меняют доступ ученика или полностью удаляют профиль.",
        ]),
        reply_markup=make_admin_student_danger_keyboard(student_id, page),
    )


def _write_to_student_result_keyboard(student_id: int, page: int | None, source: str = "card"):
    if page is not None:
        target = f"admin:student_{source}:{student_id}:{page}" if source in {"actions", "settings", "danger"} else f"admin:student_card:{student_id}:{page}"
        return make_back_button_keyboard("◀️ К ученику", target)
    return back_to_admin_keyboard


def _followup_prompt_context(lesson: dict | None) -> tuple[str, str]:
    student_name = q(lesson.get("full_name")) if lesson else "—"
    lesson_label = format_datetime(lesson.get("lesson_date")) if lesson else "—"
    return student_name, lesson_label


async def _render_admin_lesson_formats(message: types.Message, db: Database):
    students = await db.get_all_students()
    if not students:
        await message.edit_text(ADMIN_LESSON_FORMATS_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
        return

    offline = [s for s in students if (s.get("lesson_format") or "online") == "offline"]
    online = [s for s in students if (s.get("lesson_format") or "online") != "offline"]

    lines = [
        "🏫 <b>Формат занятий</b>",
        "",
        f"🏠 Очные: <b>{len(offline)}</b>",
        f"💻 Онлайн: <b>{len(online)}</b>",
        "",
    ]
    if offline:
        lines.append("Очные ученики:")
        for student in offline:
            lines.append(f"• {q(student['full_name'])}")
        lines.append("")
    lines.append("Нажмите на ученика ниже, чтобы переключить формат.")

    await message.edit_text(
        "\n".join(lines),
        reply_markup=make_admin_lesson_formats_keyboard(students),
    )


async def _render_admin_speech_styles(message: types.Message, db: Database):
    students = await db.get_all_students()
    if not students:
        await message.edit_text(ADMIN_SPEECH_STYLES_EMPTY_TEXT, reply_markup=back_to_admin_keyboard)
        return

    formal = [s for s in students if normalize_speech_style(s.get("speech_style")) == "formal"]
    informal = [s for s in students if normalize_speech_style(s.get("speech_style")) == "informal"]

    lines = [
        "🗣 <b>Обращение с учениками</b>",
        "",
        f"🫱 На Вы: <b>{len(formal)}</b>",
        f"🤝 На ты: <b>{len(informal)}</b>",
        "",
    ]
    if formal:
        lines.append("Сейчас на Вы:")
        for student in formal:
            lines.append(f"• {q(student['full_name'])}")
        lines.append("")
    lines.append("Нажмите на ученика ниже, чтобы переключить обращение.")

    await message.edit_text(
        "\n".join(lines),
        reply_markup=make_admin_speech_styles_keyboard(students),
    )


async def _render_admin_pairs_page(message: types.Message, db: Database):
    get_pairs = getattr(db, "get_student_pairs_overview", None)
    pairs = list(await get_pairs() or []) if callable(get_pairs) else []
    await message.edit_text(
        build_admin_pairs_page_text(pairs),
        reply_markup=make_admin_pairs_list_keyboard(pairs),
    )


async def _render_admin_pair_card(message: types.Message, db: Database, pair_id: int):
    get_pair = getattr(db, "get_student_pair", None)
    pair = await get_pair(pair_id) if callable(get_pair) else None
    if not pair:
        await message.edit_text(
            "⚠️ Пара не найдена или уже деактивирована.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    await message.edit_text(
        build_admin_pair_card_text(pair),
        reply_markup=make_admin_pair_card_keyboard(pair),
    )


@router.callback_query(lambda c: c.data == "admin:students")
async def admin_students(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter="all",
        admin_students_query="",
        admin_students_sort="name",
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:page:"))
async def admin_students_page(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    page = int(callback_query.data.split(":")[3])
    await _render_admin_students_page(callback_query.message, db, page=page, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:filter:"))
async def admin_students_filter(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filter_key = _normalize_admin_students_filter(callback_query.data.split(":")[3])
    _, query, sort_key = await _get_admin_students_view_state(state)
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query=query,
        admin_students_sort=sort_key,
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:students:sort:"))
async def admin_students_sort(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    sort_key = _normalize_admin_students_sort(callback_query.data.split(":")[3])
    filter_key, query, _ = await _get_admin_students_view_state(state)
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query=query,
        admin_students_sort=sort_key,
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:reset")
async def admin_students_reset(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter="all",
        admin_students_query="",
        admin_students_sort="name",
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:search_clear")
async def admin_students_search_clear(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filter_key, _, sort_key = await _get_admin_students_view_state(state)
    await state.set_state(AdminStudentsDirectory.browsing)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query="",
        admin_students_sort=sort_key,
        admin_students_page=0,
    )
    await _render_admin_students_page(callback_query.message, db, page=0, state=state)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:search")
async def admin_students_search_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filter_key, query, sort_key = await _get_admin_students_view_state(state)
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    hint_lines = []
    if query:
        hint_lines.extend([
            f"Текущий поиск: <b>{q(query)}</b>",
            "",
        ])

    await state.set_state(AdminStudentsDirectory.waiting_for_search)
    await state.update_data(
        admin_students_filter=filter_key,
        admin_students_query=query,
        admin_students_sort=sort_key,
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await callback_query.message.edit_text(
        "\n".join([
            "🔎 <b>Поиск ученика</b>",
            "",
            *hint_lines,
            "Введите имя, часть имени, язык, уровень или Telegram ID одним сообщением.",
        ]),
        reply_markup=make_back_button_keyboard("◀️ К списку учеников", "admin:students:search_back"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:students:search_back")
async def admin_students_search_back(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    page = int(data.get("admin_students_page") or 0)
    await state.set_state(AdminStudentsDirectory.browsing)
    await _render_admin_students_page(callback_query.message, db, page=page, state=state)
    await callback_query.answer()


@router.message(StateFilter(AdminStudentsDirectory.waiting_for_search))
async def admin_students_search_submit(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Поиск доступен только администратору.", reply_markup=back_to_admin_keyboard)
        return

    query = _normalize_admin_students_query(message.text)
    if not query:
        await message.answer(
            "⚠️ Введите имя или часть имени.",
            reply_markup=make_back_button_keyboard("◀️ К списку учеников", "admin:students:search_back"),
        )
        return

    data = await state.get_data()
    origin_chat_id = data.get("admin_origin_chat_id")
    origin_message_id = data.get("admin_origin_message_id")

    await state.update_data(admin_students_query=query, admin_students_page=0)
    await state.set_state(AdminStudentsDirectory.browsing)

    if origin_chat_id is None or origin_message_id is None:
        await message.answer("⚠️ Не удалось вернуть список. Откройте раздел «Ученики» заново.", reply_markup=back_to_admin_keyboard)
        return

    target = MessageEditor(message.bot, origin_chat_id, origin_message_id)
    await _render_admin_students_page(target, db, page=0, state=state)


@router.callback_query(lambda c: c.data == "admin:pairs")
async def admin_pairs(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_pairs_page(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:pairs:add")
async def admin_pair_create_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    students = list(await db.get_all_students() or [])
    if not students:
        await callback_query.message.edit_text(
            ADMIN_NO_ACTIVE_STUDENTS_TEXT,
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await state.clear()
    await callback_query.message.edit_text(
        "\n".join([
            "👥 <b>Создать учебную пару</b>",
            "",
            "Сначала выберите основного контактного ученика.",
            "Через него будут идти общий баланс, расписание и домашние задания.",
        ]),
        reply_markup=make_admin_pair_primary_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:pairs:add_primary:"))
async def admin_pair_create_primary_selected(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    db: Database,
):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    primary_student_id = int(callback_query.data.split(":")[3])
    student = await db.get_user(primary_student_id)
    if not student or student.get("role") != "student" or student.get("is_active") is False:
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        pair_primary_student_id=primary_student_id,
        pair_primary_student_name=student["full_name"],
    )
    await state.set_state(AdminCreatePair.waiting_for_partner_name)
    await callback_query.message.edit_text(
        "\n".join([
            "👥 <b>Создать учебную пару</b>",
            "",
            f"Основной контакт: <b>{q(student['full_name'])}</b>",
            "",
            "Введите имя второго участника пары.",
            "Если у него нет Telegram-профиля в боте, это нормально.",
        ]),
        reply_markup=make_back_button_keyboard("◀️ К парам", "admin:pairs"),
    )
    await callback_query.answer()


@router.message(StateFilter(AdminCreatePair.waiting_for_partner_name))
async def admin_pair_create_partner_entered(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Создание пары доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    partner_name = (message.text or "").strip()
    if len(partner_name) < 2:
        await message.answer(
            "⚠️ Введите имя второго участника пары.",
            reply_markup=make_back_button_keyboard("◀️ К парам", "admin:pairs"),
        )
        return

    data = await state.get_data()
    primary_student_id = int(data["pair_primary_student_id"])
    primary_student_name = data["pair_primary_student_name"]
    create_pair = getattr(db, "create_student_pair", None)
    if not callable(create_pair):
        await state.clear()
        await message.answer("⚠️ В этой версии БД пары недоступны.", reply_markup=back_to_admin_keyboard)
        return

    pair_id = await create_pair(
        primary_student_id,
        primary_student_name,
        partner_name,
        onboarding_source="admin",
    )
    pair = await db.get_student_pair(pair_id)
    await state.clear()
    await message.answer(
        build_action_result_text(
            "Учебная пара создана",
            f"👥 <b>{q(primary_student_name)}</b> + <b>{q(partner_name)}</b>\n"
            "Баланс, темп и домашние задания будут вестись общими через основной профиль.",
            next_step="Пара уже появилась в разделе «Пары».",
        ),
        reply_markup=make_admin_pair_card_keyboard(pair),
    )


@router.callback_query(lambda c: c.data.startswith("admin:pair_invite:"))
async def admin_pair_invite_link(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    pair_id = int(callback_query.data.split(":")[2])
    ensure_invite = getattr(db, "ensure_student_pair_invite", None)
    if not callable(ensure_invite):
        await callback_query.answer("В этой версии БД ссылки для пары недоступны.", show_alert=True)
        return

    invite = await ensure_invite(pair_id)
    if not invite:
        await callback_query.message.edit_text(
            "⚠️ Не нашёл второго участника в этой паре.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    payload = f"pair_{invite['invite_token']}"
    try:
        bot_me = await callback_query.bot.get_me()
        bot_username = getattr(bot_me, "username", None)
    except Exception:
        bot_username = None
    invite_entry = f"https://t.me/{bot_username}?start={payload}" if bot_username else f"/start {payload}"

    pair = await db.get_student_pair(pair_id)
    await callback_query.message.edit_text(
        "\n".join([
            "🔗 <b>Ссылка для второго участника</b>",
            "",
            f"Пара: <b>{q(invite['title'])}</b>",
            f"Кого подключаем: <b>{q(invite['member_name'])}</b>",
            "",
            f"<code>{invite_entry}</code>",
            "",
            "Отправьте эту ссылку второму участнику. После открытия бот привяжет его Telegram к паре, "
            "а баланс, расписание и ДЗ останутся общими через основной профиль.",
        ]),
        reply_markup=make_admin_pair_card_keyboard(pair) if pair else back_to_admin_keyboard,
    )
    await callback_query.answer("Ссылка готова.")


@router.callback_query(lambda c: c.data.startswith("admin:pair:"))
async def admin_pair_card(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    pair_id = int(callback_query.data.split(":")[2])
    await _render_admin_pair_card(callback_query.message, db, pair_id)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_card:"))
async def admin_student_card(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_card(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_actions:"))
async def admin_student_actions(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_actions(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_settings:"))
async def admin_student_settings(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_settings(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_danger:"))
async def admin_student_danger(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":")
    await _render_admin_student_danger(callback_query.message, db, int(student_id_str), int(page_str))
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:write_to_student:"))
async def admin_write_to_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    parts = callback_query.data.split(":")
    student_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    source = parts[4] if len(parts) > 4 else "card"
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        student_name=student["full_name"],
        admin_return_view=(
            f"admin:student_{source}:{student_id}:{page}"
            if page is not None and source in {"actions", "settings", "danger"}
            else (f"admin:student_card:{student_id}:{page}" if page is not None else None)
        ),
        admin_origin_chat_id=origin_chat_id if page is not None else None,
        admin_origin_message_id=origin_message_id if page is not None else None,
        admin_student_card_page=page,
        admin_student_card_source=source,
    )
    await state.set_state(AdminWriteToStudent.waiting_for_message)
    await callback_query.message.edit_text(
        f"✉️ Отправьте сообщение для ученика <b>{q(student['full_name'])}</b>.\n\n"
        "Можно отправить текст, GIF, стикер, фото, документ, голосовое или видео.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_duration:"))
async def admin_student_duration_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, student_id_str, page_str = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return

    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        student_name=student["full_name"],
        admin_return_view=f"admin:student_settings:{student_id}:{page}",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
        admin_student_card_page=page,
        admin_student_card_source="settings",
    )
    await state.set_state(AdminLessonFollowup.waiting_for_lesson_duration)
    await callback_query.message.edit_text(
        f"⏱ Введите длительность урока для <b>{q(student['full_name'])}</b> в минутах.\n\n"
        "Разрешён диапазон: <code>30..180</code>.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminWriteToStudent.waiting_for_message))
async def admin_write_to_student_send(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Отправка доступна только администратору.", reply_markup=back_to_admin_keyboard)
        return

    payload = extract_broadcast_payload(message)
    if not payload:
        await message.answer(
            "⚠️ Отправьте текст, GIF, стикер или другое сообщение, которое нужно переслать ученику.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data["student_id"]
    page = data.get("admin_student_card_page")
    source = data.get("admin_student_card_source", "card")
    student = await db.get_user(student_id)
    if not student or student["role"] != "student":
        await state.clear()
        await message.answer("⚠️ Ученик не найден.", reply_markup=back_to_admin_keyboard)
        return

    try:
        if payload["mode"] == "copy":
            await message.bot.copy_message(
                chat_id=student_id,
                from_chat_id=payload["source_chat_id"],
                message_id=payload["source_message_id"],
                reply_markup=make_teacher_reply_keyboard("teacher_message"),
            )
        else:
            await message.bot.send_message(
                student_id,
                payload["text"],
                reply_markup=make_teacher_reply_keyboard("teacher_message"),
            )
    except Exception:
        await message.answer(
            "⚠️ Не удалось отправить сообщение ученику. Попробуйте ещё раз.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await state.clear()
    await restore_admin_view(
        message.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )
    await message.answer(
        build_action_result_text(
            "Сообщение отправлено",
            f"Ученик: <b>{q(student['full_name'])}</b>.",
            next_step="При необходимости можно сразу отправить ещё одно сообщение из карточки ученика.",
        ),
        reply_markup=_write_to_student_result_keyboard(student_id, page, source),
    )


@router.message(StateFilter(AdminLessonFollowup.waiting_for_lesson_duration))
async def admin_student_duration_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Изменение доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    try:
        minutes = int((message.text or "").strip())
    except ValueError:
        minutes = 0

    if not 30 <= minutes <= 180:
        await message.answer(
            "⚠️ Нужна целая длительность в диапазоне <code>30..180</code> минут.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    student_id = data["student_id"]
    student_name = q(data.get("student_name") or student_id)
    page = data.get("admin_student_card_page")
    source = data.get("admin_student_card_source", "card")
    await db.set_lesson_duration(student_id, minutes)

    await state.clear()
    await restore_admin_view(
        message.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )
    await message.answer(
        build_action_result_text(
            "Длительность урока обновлена",
            f"👤 Ученик: <b>{student_name}</b>\n⏱ Новая длительность: <b>{minutes} мин</b>",
            next_step="Новая длительность уже будет учитываться в post-lesson сообщениях.",
        ),
        reply_markup=_write_to_student_result_keyboard(student_id, page, source),
    )


@router.callback_query(lambda c: c.data.startswith("lesson_followup:comment:"))
async def lesson_followup_comment_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    lesson_id = int(callback_query.data.split(":")[2])
    lesson = await db.get_lesson_context(lesson_id)
    if not lesson:
        await callback_query.answer("Урок не найден.", show_alert=True)
        return

    student_name, lesson_label = _followup_prompt_context(lesson)
    await state.clear()
    await state.update_data(
        followup_lesson_id=lesson_id,
        followup_student_id=lesson["student_id"],
        followup_student_name=student_name,
        followup_lesson_label=lesson_label,
    )
    await state.set_state(AdminLessonFollowup.waiting_for_lesson_comment)
    await callback_query.message.edit_text(
        f"💬 Напишите приватный комментарий по уроку с <b>{student_name}</b>.\n"
        f"📅 Урок: <b>{lesson_label}</b>",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminLessonFollowup.waiting_for_lesson_comment))
async def lesson_followup_comment_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Сохранение доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    comment_html = message_to_html(message)
    if not comment_html:
        await message.answer(
            "⚠️ Пришлите текстовый комментарий по уроку.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    await db.save_teacher_comment(data["followup_lesson_id"], comment_html)
    await state.clear()
    await message.answer(
        build_action_result_text(
            "Комментарий сохранён",
            f"👤 Ученик: <b>{data['followup_student_name']}</b>\n📅 Урок: <b>{data['followup_lesson_label']}</b>",
            next_step="Комментарий привязан только к этому уроку и не попадёт в reminder перед следующим занятием.",
        ),
        reply_markup=back_to_admin_keyboard,
    )


@router.callback_query(lambda c: c.data.startswith("lesson_followup:bookmark:"))
async def lesson_followup_bookmark_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, lesson_id_str, student_id_str = callback_query.data.split(":")
    lesson_id = int(lesson_id_str)
    student_id = int(student_id_str)
    lesson = await db.get_lesson_context(lesson_id)
    if not lesson or lesson["student_id"] != student_id:
        await callback_query.answer("Урок или ученик не найдены.", show_alert=True)
        return

    student_name, lesson_label = _followup_prompt_context(lesson)
    await state.clear()
    await state.update_data(
        followup_lesson_id=lesson_id,
        followup_student_id=student_id,
        followup_student_name=student_name,
        followup_lesson_label=lesson_label,
    )
    await state.set_state(AdminLessonFollowup.waiting_for_lesson_bookmark)
    await callback_query.message.edit_text(
        f"📖 Напишите закладку по учебнику или книге для <b>{student_name}</b>.\n"
        f"📅 Последний урок: <b>{lesson_label}</b>\n\n"
        "Этот текст придёт вам перед следующим занятием с этим учеником.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminLessonFollowup.waiting_for_lesson_bookmark))
async def lesson_followup_bookmark_save(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Сохранение доступно только администратору.", reply_markup=back_to_admin_keyboard)
        return

    bookmark_html = message_to_html(message)
    if not bookmark_html:
        await message.answer(
            "⚠️ Пришлите текстовую закладку по учебнику или книге.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    await db.save_student_bookmark(
        data["followup_student_id"],
        data["followup_lesson_id"],
        bookmark_html,
        "saved",
    )
    await state.clear()
    await message.answer(
        build_action_result_text(
            "Закладка сохранена",
            f"👤 Ученик: <b>{data['followup_student_name']}</b>\n📅 Последний урок: <b>{data['followup_lesson_label']}</b>",
            next_step="Перед следующим уроком бот пришлёт вам эту закладку автоматически.",
        ),
        reply_markup=back_to_admin_keyboard,
    )


@router.callback_query(lambda c: c.data.startswith("lesson_followup:no_material:"))
async def lesson_followup_no_material(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, _, lesson_id_str, student_id_str = callback_query.data.split(":")
    lesson_id = int(lesson_id_str)
    student_id = int(student_id_str)
    lesson = await db.get_lesson_context(lesson_id)
    if not lesson or lesson["student_id"] != student_id:
        await callback_query.answer("Урок или ученик не найдены.", show_alert=True)
        return

    await db.save_student_bookmark(student_id, lesson_id, None, "no_material")
    await callback_query.message.edit_text(
        build_action_result_text(
            "Закладка очищена",
            f"👤 Ученик: <b>{q(lesson['full_name'])}</b>\n📅 Последний урок: <b>{format_datetime(lesson.get('lesson_date'))}</b>",
            next_step="Перед следующим уроком бот всё равно напомнит, что по учебнику или книге в прошлый раз не работали.",
        ),
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer("Отмечено: без учебника/книги")


@router.callback_query(lambda c: c.data.startswith("admin:student_format:"))
async def admin_student_format_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, target_format = callback_query.data.split(":")
    if target_format not in {"online", "offline"}:
        await callback_query.answer("Неизвестный формат.", show_alert=True)
        return
    student_id = int(student_id_str)
    page = int(page_str)
    await db.set_lesson_format(student_id, target_format)
    await _render_admin_student_settings(callback_query.message, db, student_id, page)
    await callback_query.answer(f"Формат переключён: {lesson_format_label(target_format)}")


@router.callback_query(lambda c: c.data.startswith("admin:student_speech_style:"))
async def admin_student_speech_style_toggle(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, target_style = callback_query.data.split(":")
    target_style = normalize_speech_style(target_style)
    student_id = int(student_id_str)
    page = int(page_str)
    await db.set_speech_style(student_id, target_style)
    await _render_admin_student_settings(callback_query.message, db, student_id, page)
    await callback_query.answer(f"Обращение переключено: {speech_style_label(target_style)}")


@router.callback_query(lambda c: c.data == "admin:lesson_formats")
async def admin_lesson_formats(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_lesson_formats(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:speech_styles")
async def admin_speech_styles(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await _render_admin_speech_styles(callback_query.message, db)
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:lesson_format_toggle:"))
async def admin_lesson_format_toggle_list(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, target_format = callback_query.data.split(":")
    if target_format not in {"online", "offline"}:
        await callback_query.answer("Неизвестный формат.", show_alert=True)
        return
    student_id = int(student_id_str)
    await db.set_lesson_format(student_id, target_format)
    await _render_admin_lesson_formats(callback_query.message, db)
    await callback_query.answer(f"Переключено: {lesson_format_label(target_format)}")


@router.callback_query(lambda c: c.data.startswith("admin:speech_style_toggle:"))
async def admin_speech_style_toggle_list(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, target_style = callback_query.data.split(":")
    target_style = normalize_speech_style(target_style)
    student_id = int(student_id_str)
    await db.set_speech_style(student_id, target_style)
    await _render_admin_speech_styles(callback_query.message, db)
    await callback_query.answer(f"Переключено: {speech_style_label(target_style)}")


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_prompt:"))
async def admin_student_deactivate_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    await callback_query.message.edit_text(
        f"🗑 <b>Деактивировать ученика {name}?</b>\n\n"
        "Ученик потеряет доступ к боту, но история занятий и оплат сохранится.",
        reply_markup=make_admin_student_danger_review_keyboard(
            f"admin:student_deactivate_review:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "⚠️ Перейти к подтверждению",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_review:"))
async def admin_student_deactivate_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Ученик <b>{name}</b> потеряет доступ к боту сразу после этого шага.",
            "История занятий и оплат сохранится.",
        ]),
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:student_deactivate_confirm:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "✅ Деактивировать ученика",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_deactivate_confirm:"))
async def admin_student_deactivate_confirm_direct(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.deactivate_student(student_id)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Ученик деактивирован",
            f"Профиль <b>{name}</b> отключён, а история занятий и оплат сохранена.",
            next_step="При необходимости ученика можно снова добавить или зарегистрировать заново.",
        ),
        reply_markup=make_back_button_keyboard("◀️ К списку учеников", f"admin:students:page:{page}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_prompt:"))
async def admin_student_delete_prompt(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    snapshot = await db.get_user_deletion_snapshot(student_id)

    await callback_query.message.edit_text(
        f"💀 <b>Удалить ученика {name}?</b>\n\n"
        f"📚 Занятий: <b>{snapshot.get('lessons', 0)}</b>\n"
        f"💳 Платежей: <b>{snapshot.get('payments_as_student', 0)}</b>\n"
        f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>\n\n"
        "Это действие необратимо.",
        reply_markup=make_admin_student_danger_review_keyboard(
            f"admin:student_delete_review:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "⚠️ Перейти к подтверждению",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_review:"))
async def admin_student_delete_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Профиль <b>{name}</b> будет удалён вместе с уроками, оплатами и домашними заданиями.",
            "После этого восстановление из интерфейса невозможно.",
        ]),
        reply_markup=make_admin_student_danger_confirm_keyboard(
            f"admin:student_delete_confirm:{student_id}:{page}",
            f"admin:student_danger:{student_id}:{page}",
            "💀 Удалить навсегда",
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:student_delete_confirm:"))
async def admin_student_delete_confirm_direct(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str = callback_query.data.split(":", 3)
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.delete_user_fully(student_id)
    await callback_query.message.edit_text(
        build_action_result_text(
            "Ученик удалён",
            f"Профиль <b>{name}</b> полностью удалён из базы.",
            next_step="Если человек снова запустит /start, он пройдёт регистрацию заново.",
        ),
        reply_markup=make_back_button_keyboard("◀️ К списку учеников", f"admin:students:page:{page}"),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:deactivate_student")
async def admin_deactivate_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(ADMIN_NO_ACTIVE_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard)
        await callback_query.answer()
        return
    await state.set_state(AdminManageStudent.waiting_for_student)
    await state.update_data(action="deactivate")
    await callback_query.message.edit_text(
        "🗑 <b>Деактивировать ученика</b>\n\nВыберите ученика:",
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:delete_student")
async def admin_delete_student_start(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    students = await db.get_all_students()
    if not students:
        await callback_query.message.edit_text(ADMIN_NO_ACTIVE_STUDENTS_TEXT, reply_markup=back_to_admin_keyboard)
        await callback_query.answer()
        return
    await state.set_state(AdminManageStudent.waiting_for_student)
    await state.update_data(action="delete")
    await callback_query.message.edit_text(
        "💀 <b>Удалить ученика</b>\n\nВыберите ученика для полного удаления:",
        reply_markup=make_student_select_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("select_student:"), StateFilter(AdminManageStudent.waiting_for_student))
async def admin_select_student_manage(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)

    data = await state.get_data()
    action = data.get("action")
    await state.clear()

    if action == "delete":
        snapshot = await db.get_user_deletion_snapshot(student_id)
        await callback_query.message.edit_text(
            f"💀 <b>Удалить ученика {name}?</b>\n\n"
            "⚠️ Будут удалены все занятия, платежи и данные.\n"
            f"📚 Занятий: <b>{snapshot.get('lessons', 0)}</b>\n"
            f"💳 Платежей: <b>{snapshot.get('payments_as_student', 0)}</b>\n"
            f"📚 Домашних заданий: <b>{snapshot.get('homework', 0)}</b>\n"
            f"🧭 Calendar-связей: <b>{snapshot.get('calendar_links', 0)}</b>\n\n"
            "После этого ученик сможет зарегистрироваться заново.",
            reply_markup=make_delete_review_keyboard(student_id),
        )
    else:
        await callback_query.message.edit_text(
            f"🗑 Деактивировать ученика <b>{name}</b>?\n\n"
            "Ученик не сможет пользоваться ботом. История платежей и занятий сохранится.",
            reply_markup=make_deactivate_review_keyboard(student_id),
        )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("deactivate_review:"))
async def admin_deactivate_student_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Ученик <b>{name}</b> потеряет доступ к боту сразу после этого шага.",
            "История платежей и занятий сохранится.",
        ]),
        reply_markup=make_deactivate_confirm_keyboard(student_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("deactivate_confirm:"))
async def admin_deactivate_student_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.deactivate_student(student_id)
    await callback_query.message.edit_text(
        f"✅ Ученик <b>{name}</b> деактивирован.\n\nИстория сохранена.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("delete_review:"))
async def admin_delete_student_review(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await callback_query.message.edit_text(
        "\n".join([
            "⚠️ <b>Финальное подтверждение</b>",
            "",
            f"Профиль <b>{name}</b> будет удалён вместе с уроками, оплатами и домашними заданиями.",
            "После этого восстановление из интерфейса невозможно.",
        ]),
        reply_markup=make_delete_confirm_keyboard(student_id),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("delete_confirm:"))
async def admin_delete_student_confirm(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    student_id = int(callback_query.data.split(":")[1])
    student = await db.get_user(student_id)
    name = q(student["full_name"]) if student else str(student_id)
    await db.delete_user_fully(student_id)
    await callback_query.message.edit_text(
        f"💀 Ученик <b>{name}</b> полностью удалён.\n\n"
        "При следующем /start он пройдёт регистрацию заново.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:add_student")
async def admin_add_student_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminAddStudent.waiting_for_name)
    await callback_query.message.edit_text(
        "👤 <b>Добавить ученика</b>\n\n"
        "Введите полное имя ученика (как оно написано в Google Calendar):\n\n"
        "Например: <code>Иван Петров</code>",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminAddStudent.waiting_for_name))
async def admin_add_student_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ Имя не может быть пустым.", reply_markup=cancel_fsm_keyboard)
        return
    await state.update_data(full_name=name)
    await state.set_state(AdminAddStudent.waiting_for_telegram_id)
    await message.answer(
        f"✅ Имя: <b>{name}</b>\n\n"
        "Теперь введите Telegram ID ученика.\n\n"
        "Если ID неизвестен — введите <code>0</code>, тогда ученик сможет "
        "войти сам через /start и его данные обновятся автоматически.",
        reply_markup=cancel_fsm_keyboard,
    )


@router.message(StateFilter(AdminAddStudent.waiting_for_telegram_id))
async def admin_add_student_id(message: types.Message, state: FSMContext, db: Database):
    try:
        telegram_id = int((message.text or "").strip())
        if telegram_id < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Введите числовой Telegram ID или <code>0</code> если неизвестен.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    full_name = data["full_name"]

    if telegram_id == 0:
        await message.answer(
            "⚠️ Добавление без Telegram ID пока не поддерживается.\n"
            "Попросите ученика написать боту /start — он зарегистрируется сам.",
            reply_markup=back_to_admin_keyboard,
        )
        await state.clear()
        return

    existing = await db.get_user(telegram_id)
    if existing:
        await state.clear()
        await message.answer(
            f"⚠️ Пользователь с ID <code>{telegram_id}</code> уже есть в базе:\n"
            f"<b>{q(existing['full_name'])}</b> ({q(existing['role'])})",
            reply_markup=back_to_admin_keyboard,
        )
        return

    if await db.is_telegram_id_blocked(telegram_id):
        await state.clear()
        await message.answer(
            f"🚫 ID <code>{telegram_id}</code> есть в списке блокировок.\n"
            "Сначала снимите блок командой <code>/unblock</code>, а потом добавляйте профиль.",
            reply_markup=back_to_admin_keyboard,
        )
        return

    async with db.pool.acquire() as conn:
        internal = is_internal_test_account(full_name=full_name, telegram_id=telegram_id)
        await conn.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, role, is_internal_account)
            VALUES ($1, $2, NULL, 'student', $3)
            """,
            telegram_id, full_name, internal,
        )

    await state.clear()
    internal_line = (
        "\n⚙️ Аккаунт помечен как внутренний тестовый и исключён из рабочей логики."
        if internal else ""
    )
    await message.answer(
        f"✅ <b>Ученик добавлен!</b>\n\n"
        f"👤 Имя: {q(full_name)}\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n\n"
        f"Теперь можно запустить /sync — занятия из Calendar привяжутся к этому ученику."
        f"{internal_line}",
        reply_markup=back_to_admin_keyboard,
    )
