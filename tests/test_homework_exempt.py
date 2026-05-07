"""Tests for homework_exempt flag and homework submission loop fixes."""
from datetime import datetime, timedelta

from keyboards.inline import (
    make_admin_homework_done_notification_keyboard,
    make_admin_student_overview_keyboard,
    make_admin_student_settings_keyboard,
    make_admin_students_list_keyboard,
)
from utils.pulse_engine import compute_student_health
from utils.touch_engine import select_touch_type
from utils.ui_text import build_admin_student_card_text, build_homework_text


# ── pulse_engine: homework_exempt suppresses no_hw_* reasons ────────────────

def _base_row(**overrides):
    row = {
        "telegram_id": 1,
        "full_name": "Иван",
        "balance": 5,
        "open_nudge_count": 0,
        "last_lesson_date": datetime.now() - timedelta(hours=48),
        "last_hw_created_at": None,
        "first_lesson_date": datetime.now() - timedelta(days=30),
        "total_lessons": 4,
        "homework_exempt": False,
    }
    row.update(overrides)
    return row


def test_no_hw_24h_red_when_not_exempt():
    row = _base_row()
    health = compute_student_health(row)
    assert "no_hw_24h" in health["reasons"]
    assert health["color"] == "red"


def test_no_hw_24h_suppressed_when_exempt():
    row = _base_row(homework_exempt=True)
    health = compute_student_health(row)
    assert "no_hw_24h" not in health["reasons"]
    assert "no_hw_6h" not in health["reasons"]


def test_no_hw_6h_suppressed_when_exempt():
    row = _base_row(
        last_lesson_date=datetime.now() - timedelta(hours=12),
        homework_exempt=True,
    )
    health = compute_student_health(row)
    assert "no_hw_6h" not in health["reasons"]


# ── touch_engine: homework_exempt skips hw_nudge ────────────────────────────

def test_select_touch_type_hw_nudge_when_not_exempt():
    result = select_touch_type({}, has_active_hw=True, streak_weeks=1, balance=5)
    assert result == "hw_nudge"


def test_select_touch_type_skips_hw_nudge_when_exempt():
    result = select_touch_type(
        {},
        has_active_hw=True,
        streak_weeks=1,
        balance=5,
        homework_exempt=True,
    )
    assert result != "hw_nudge"


def test_select_touch_type_falls_through_to_motivation_when_exempt_with_streak():
    result = select_touch_type(
        {},
        has_active_hw=True,
        streak_weeks=5,
        balance=5,
        homework_exempt=True,
    )
    assert result == "motivation"


# ── ui_text: exempt-aware empty homework text ───────────────────────────────

def test_build_homework_text_default_empty():
    text = build_homework_text([], "active")
    assert "не задаются" not in text
    assert "Активные задания" in text


def test_build_homework_text_exempt_empty():
    text = build_homework_text([], "active", homework_exempt=True)
    assert "не задаются" in text


def test_build_homework_text_with_items_ignores_exempt():
    items = [{"id": 1, "title": "Read p.1", "description": "x", "deadline": datetime.now()}]
    exempt_text = build_homework_text(items, "active", homework_exempt=True)
    plain_text = build_homework_text(items, "active")
    assert "не задаются" not in exempt_text
    # Both should render the same when items are present
    assert exempt_text == plain_text


def test_build_homework_text_done_status_ignores_exempt():
    text = build_homework_text([], "done", homework_exempt=True)
    # Exempt explanation is for active list only
    assert "не задаются" not in text


# ── keyboards: settings keyboard exposes exempt toggle ──────────────────────

def _flatten_callbacks(keyboard):
    return [btn.callback_data for row in keyboard.inline_keyboard for btn in row]


def test_settings_keyboard_shows_set_to_exempt_when_not_exempt():
    kb = make_admin_student_settings_keyboard(42, 0, homework_exempt=False)
    callbacks = _flatten_callbacks(kb)
    assert "admin:student_homework_exempt:42:0:1" in callbacks
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("📚 ДЗ: задаю" in label for label in labels)


def test_settings_keyboard_shows_set_to_normal_when_exempt():
    kb = make_admin_student_settings_keyboard(42, 0, homework_exempt=True)
    callbacks = _flatten_callbacks(kb)
    assert "admin:student_homework_exempt:42:0:0" in callbacks
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("🚫 ДЗ: не задаю" in label for label in labels)


def test_admin_done_notification_keyboard_has_unmark_and_open():
    kb = make_admin_homework_done_notification_keyboard(99)
    callbacks = _flatten_callbacks(kb)
    assert "hw_unmark_done:99" in callbacks
    assert "admin:homework_manage:99" in callbacks


# ── Visibility: card overview keyboard exposes one-click toggle ─────────────

def test_overview_keyboard_shows_set_to_exempt_when_not_exempt():
    kb = make_admin_student_overview_keyboard(42, 0, homework_exempt=False)
    callbacks = _flatten_callbacks(kb)
    assert "admin:student_homework_exempt_card:42:0:1" in callbacks
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("📚 ДЗ-режим: задаю" in label for label in labels)


def test_overview_keyboard_shows_set_to_normal_when_exempt():
    kb = make_admin_student_overview_keyboard(42, 0, homework_exempt=True)
    callbacks = _flatten_callbacks(kb)
    assert "admin:student_homework_exempt_card:42:0:0" in callbacks
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("🚫 ДЗ-режим: не задаю" in label for label in labels)


def test_students_list_keyboard_marks_exempt_with_badge():
    students = [
        {"telegram_id": 1, "full_name": "Иван", "homework_exempt": False},
        {"telegram_id": 2, "full_name": "Мария", "homework_exempt": True},
    ]
    kb = make_admin_students_list_keyboard(students, page=0, page_size=10)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    ivan_label = next(label for label in labels if "Иван" in label)
    maria_label = next(label for label in labels if "Мария" in label)
    assert "🚫" not in ivan_label
    assert "🚫" in maria_label


def test_admin_student_card_text_shows_homework_mode():
    student = {
        "full_name": "Иван",
        "telegram_id": 1,
        "lesson_format": "online",
        "speech_style": "formal",
        "language": "english",
        "level": "B1",
        "lesson_reminders": "enabled",
        "homework_exempt": True,
        "lessons_completed_count": 5,
        "lesson_duration_minutes": 60,
    }
    text = build_admin_student_card_text(student, balance=3, next_lesson=None, pair=None)
    assert "Режим ДЗ" in text
    assert "не задаю" in text


def test_admin_student_card_text_shows_default_homework_mode():
    student = {
        "full_name": "Иван",
        "telegram_id": 1,
        "lesson_format": "online",
        "speech_style": "formal",
        "language": "english",
        "level": "B1",
        "lesson_reminders": "enabled",
        "lessons_completed_count": 5,
        "lesson_duration_minutes": 60,
    }
    text = build_admin_student_card_text(student, balance=3, next_lesson=None, pair=None)
    assert "Режим ДЗ" in text
    assert "задаю" in text
    assert "не задаю" not in text
