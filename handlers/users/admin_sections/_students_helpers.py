"""Общие вспомогательные функции и константы для раздела «Ученики».

Этот модуль не содержит Router — только чистые функции и константы.
"""
from aiogram import types
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import q
from keyboards.inline import (
    back_to_admin_keyboard,
    make_admin_lesson_formats_keyboard,
    make_admin_pair_card_keyboard,
    make_admin_pairs_list_keyboard,
    make_admin_speech_styles_keyboard,
    make_admin_student_actions_keyboard,
    make_admin_student_card_keyboard,
    make_admin_student_danger_keyboard,
    make_admin_student_settings_keyboard,
    make_admin_students_list_keyboard,
    make_back_button_keyboard,
)
from states.registration import AdminStudentsDirectory
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_LESSON_FORMATS_EMPTY_TEXT,
    ADMIN_NO_ACTIVE_STUDENTS_TEXT,
    ADMIN_SPEECH_STYLES_EMPTY_TEXT,
    ADMIN_STUDENTS_EMPTY_TEXT,
    build_admin_pair_card_text,
    build_admin_pairs_page_text,
    build_admin_students_page_text,
    build_admin_student_card_text,
    format_datetime,
    lesson_format_label,
)
from utils.speech import normalize_speech_style, speech_style_label

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

    # Get pricing rate for display
    pricing_rate = None
    rate_id = student.get("pricing_rate_id")
    if rate_id:
        pricing_rate = await db.get_pricing_rate_by_id(rate_id)

    # Progress block
    progress_block = None
    get_progress = getattr(db, "get_student_progress", None)
    if callable(get_progress):
        from utils.achievements import build_admin_progress_text
        from utils.pulse_engine import _compute_streak_weeks
        from datetime import datetime as _dt

        progress = await get_progress(student_id)
        achievements = await db.get_student_achievements(student_id)
        feedback = await db.get_recent_feedback(student_id, limit=10)
        first_lesson = progress.get("first_lesson_date")
        last_lesson = progress.get("last_lesson_date")
        total_lessons = int(progress.get("total_lessons") or 0)
        streak = _compute_streak_weeks(first_lesson, last_lesson, total_lessons, _dt.now())
        progress_block = build_admin_progress_text(progress, achievements, streak, feedback)

    await message.edit_text(
        build_admin_student_card_text(
            student, balance, next_lesson, pair=pair,
            tariff_text=student.get("tariff_text"),
            pricing_rate=pricing_rate,
            progress_block=progress_block,
        ),
        reply_markup=make_admin_student_card_keyboard(
            student_id,
            page,
            homework_exempt=bool(student.get("homework_exempt")),
        ),
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
            student_type=student.get("student_type") or "adult",
            preferred_name=student.get("preferred_name"),
            homework_exempt=bool(student.get("homework_exempt")),
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
