"""Tests for utils/pulse_engine.py: traffic-light logic, text formatting, quiet hours."""
from datetime import datetime, timedelta, date

from utils.pulse_engine import (
    compute_student_health,
    build_pulse_text,
    build_briefing_text,
    should_send_briefing,
    get_most_urgent_student_id,
    is_quiet_hours,
    next_active_time,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_row(
    *,
    full_name: str = "Тест",
    telegram_id: int = 100,
    balance: int = 5,
    last_lesson_date: datetime | None = None,
    last_hw_created_at: datetime | None = None,
    first_lesson_date: datetime | None = None,
    total_lessons: int = 10,
    open_nudge_count: int = 0,
    is_pair: bool = False,
    pair_title: str | None = None,
) -> dict:
    now = datetime.now()
    return {
        "telegram_id": telegram_id,
        "full_name": full_name,
        "speech_style": None,
        "touches_enabled": True,
        "goal_text": None,
        "is_pair": is_pair,
        "pair_title": pair_title,
        "primary_student_id": telegram_id,
        "last_lesson_date": last_lesson_date or (now - timedelta(days=2)),
        "first_lesson_date": first_lesson_date or (now - timedelta(days=60)),
        "total_lessons": total_lessons,
        "last_hw_created_at": last_hw_created_at or now,
        "balance": balance,
        "open_nudge_count": open_nudge_count,
    }


# ── Traffic light: balance ───────────────────────────────────────────────────

class TestBalanceColor:
    def test_balance_0_is_red(self):
        row = _make_row(balance=0)
        h = compute_student_health(row)
        assert h["color"] == "red"
        assert "balance_0" in h["reasons"]

    def test_balance_1_is_yellow(self):
        row = _make_row(balance=1)
        h = compute_student_health(row)
        assert h["color"] == "yellow"
        assert "balance_1" in h["reasons"]

    def test_balance_2_is_green(self):
        row = _make_row(balance=2)
        h = compute_student_health(row)
        assert h["color"] == "green"

    def test_balance_10_is_green(self):
        row = _make_row(balance=10)
        h = compute_student_health(row)
        assert h["color"] == "green"


# ── Traffic light: HW timing ────────────────────────────────────────────────

class TestHwTimingColor:
    def test_no_hw_over_24h_is_red(self):
        now = datetime.now()
        row = _make_row(
            last_lesson_date=now - timedelta(hours=25),
            last_hw_created_at=now - timedelta(hours=30),  # HW before lesson
        )
        h = compute_student_health(row, now=now)
        assert h["color"] == "red"
        assert "no_hw_24h" in h["reasons"]

    def test_no_hw_over_6h_is_yellow(self):
        now = datetime.now()
        row = _make_row(
            last_lesson_date=now - timedelta(hours=8),
            last_hw_created_at=now - timedelta(hours=10),  # HW before lesson
        )
        h = compute_student_health(row, now=now)
        assert h["color"] == "yellow"
        assert "no_hw_6h" in h["reasons"]

    def test_hw_sent_after_lesson_is_green(self):
        now = datetime.now()
        row = _make_row(
            last_lesson_date=now - timedelta(hours=8),
            last_hw_created_at=now - timedelta(hours=1),  # HW after lesson
        )
        h = compute_student_health(row, now=now)
        assert h["color"] == "green"

    def test_no_hw_ever_and_recent_lesson_is_yellow(self):
        now = datetime.now()
        row = _make_row(
            last_lesson_date=now - timedelta(hours=8),
            last_hw_created_at=None,
        )
        row["last_hw_created_at"] = None
        h = compute_student_health(row, now=now)
        assert h["color"] in ("yellow", "red")


# ── Traffic light: lesson gap ────────────────────────────────────────────────

class TestLessonGapColor:
    def test_no_lessons_over_14d_is_red(self):
        now = datetime.now()
        row = _make_row(last_lesson_date=now - timedelta(days=15))
        h = compute_student_health(row, now=now)
        assert h["color"] == "red"
        assert "no_lesson_14d" in h["reasons"]

    def test_no_lessons_10d_is_yellow(self):
        now = datetime.now()
        row = _make_row(last_lesson_date=now - timedelta(days=10))
        h = compute_student_health(row, now=now)
        assert h["color"] == "yellow"
        assert "no_lesson_7d" in h["reasons"]

    def test_recent_lesson_is_green(self):
        now = datetime.now()
        row = _make_row(last_lesson_date=now - timedelta(days=3))
        h = compute_student_health(row, now=now)
        assert h["color"] == "green"


# ── Combination: worst color wins ───────────────────────────────────────────

class TestCombination:
    def test_multiple_red_reasons(self):
        now = datetime.now()
        row = _make_row(
            balance=0,
            last_lesson_date=now - timedelta(days=15),
        )
        h = compute_student_health(row, now=now)
        assert h["color"] == "red"
        assert "balance_0" in h["reasons"]
        assert "no_lesson_14d" in h["reasons"]

    def test_red_overrides_yellow(self):
        now = datetime.now()
        row = _make_row(
            balance=0,  # red
            last_lesson_date=now - timedelta(days=3),  # green
        )
        h = compute_student_health(row, now=now)
        assert h["color"] == "red"


# ── Streak ───────────────────────────────────────────────────────────────────

class TestStreak:
    def test_streak_weeks_with_recent_activity(self):
        now = datetime.now()
        row = _make_row(
            first_lesson_date=now - timedelta(days=28),
            last_lesson_date=now - timedelta(days=2),
            total_lessons=10,
        )
        h = compute_student_health(row, now=now)
        assert h["streak_weeks"] >= 3

    def test_no_streak_if_old_last_lesson(self):
        now = datetime.now()
        row = _make_row(
            first_lesson_date=now - timedelta(days=60),
            last_lesson_date=now - timedelta(days=15),
            total_lessons=10,
        )
        h = compute_student_health(row, now=now)
        assert h["streak_weeks"] == 0


# ── Pair display ─────────────────────────────────────────────────────────────

class TestPairDisplay:
    def test_pair_uses_pair_title(self):
        row = _make_row(is_pair=True, pair_title="Игорь + Маша")
        h = compute_student_health(row)
        assert h["is_pair"] is True
        assert h["pair_title"] == "Игорь + Маша"


# ── build_pulse_text ─────────────────────────────────────────────────────────

class TestBuildPulseText:
    def test_empty_list(self):
        text = build_pulse_text([], today_date=date(2026, 5, 4))
        assert "Пульс" in text
        assert "Нет активных учеников" in text

    def test_with_students(self):
        now = datetime.now()
        health_list = [
            compute_student_health(
                _make_row(full_name="Аня", balance=0, last_lesson_date=now - timedelta(days=5)),
                now=now,
            ),
            compute_student_health(_make_row(full_name="Катя", balance=5), now=now),
        ]
        text = build_pulse_text(health_list, today_date=date(2026, 5, 4))
        assert "Аня" in text
        assert "Катя" in text
        assert "баланс 0" in text

    def test_contains_counter_line(self):
        now = datetime.now()
        health_list = [
            compute_student_health(_make_row(full_name="A", balance=0), now=now),
            compute_student_health(_make_row(full_name="B", balance=5), now=now),
        ]
        text = build_pulse_text(health_list, today_date=date(2026, 5, 4))
        # Should contain color counter at bottom
        assert "\U0001f534" in text  # red circle
        assert "\U0001f7e2" in text  # green circle


# ── build_briefing_text ──────────────────────────────────────────────────────

class TestBuildBriefingText:
    def test_with_lessons_and_problems(self):
        now = datetime.now()
        lessons = [
            {"lesson_date": now.replace(hour=14, minute=0), "full_name": "Аня", "is_pair": False, "pair_title": None},
        ]
        health_list = [
            compute_student_health(_make_row(full_name="Аня", balance=0), now=now),
        ]
        text = build_briefing_text(health_list, lessons, today_date=date(2026, 5, 5))
        assert "Доброе утро" in text
        assert "Уроки сегодня: 1" in text
        assert "Аня" in text
        assert "Требует внимания" in text

    def test_problems_only_no_lessons(self):
        now = datetime.now()
        health_list = [
            compute_student_health(_make_row(full_name="Дима", balance=0), now=now),
        ]
        text = build_briefing_text(health_list, [], today_date=date(2026, 5, 5))
        assert "Доброе утро" in text
        assert "Требует внимания" in text
        assert "Дима" in text


# ── should_send_briefing ─────────────────────────────────────────────────────

class TestShouldSendBriefing:
    def test_no_lessons_no_problems_skip(self):
        health_list = [{"color": "green"}]
        assert should_send_briefing(health_list, []) is False

    def test_has_lessons_send(self):
        health_list = [{"color": "green"}]
        assert should_send_briefing(health_list, [{"some": "lesson"}]) is True

    def test_has_problems_send(self):
        health_list = [{"color": "red"}]
        assert should_send_briefing(health_list, []) is True


# ── get_most_urgent_student_id ───────────────────────────────────────────────

class TestMostUrgent:
    def test_returns_first_red(self):
        health_list = [
            {"color": "red", "telegram_id": 100},
            {"color": "yellow", "telegram_id": 200},
        ]
        assert get_most_urgent_student_id(health_list) == 100

    def test_returns_none_if_no_red(self):
        health_list = [
            {"color": "green", "telegram_id": 100},
        ]
        assert get_most_urgent_student_id(health_list) is None


# ── Quiet hours ──────────────────────────────────────────────────────────────

class TestQuietHours:
    def test_23h_is_quiet(self):
        dt = datetime(2026, 5, 4, 23, 0)
        assert is_quiet_hours(dt) is True

    def test_3h_is_quiet(self):
        dt = datetime(2026, 5, 4, 3, 0)
        assert is_quiet_hours(dt) is True

    def test_7h_is_quiet_for_admin(self):
        dt = datetime(2026, 5, 4, 7, 0)
        assert is_quiet_hours(dt, for_student=False) is True

    def test_8h_is_not_quiet_for_admin(self):
        dt = datetime(2026, 5, 4, 8, 0)
        assert is_quiet_hours(dt, for_student=False) is False

    def test_8h_is_quiet_for_student(self):
        dt = datetime(2026, 5, 4, 8, 0)
        assert is_quiet_hours(dt, for_student=True) is True

    def test_9h_is_not_quiet_for_student(self):
        dt = datetime(2026, 5, 4, 9, 0)
        assert is_quiet_hours(dt, for_student=True) is False

    def test_12h_is_not_quiet(self):
        dt = datetime(2026, 5, 4, 12, 0)
        assert is_quiet_hours(dt) is False

    def test_next_active_time_from_midnight(self):
        dt = datetime(2026, 5, 4, 0, 30)
        result = next_active_time(dt)
        assert result.hour == 8
        assert result.day == 4

    def test_next_active_time_from_23h(self):
        dt = datetime(2026, 5, 4, 23, 30)
        result = next_active_time(dt)
        assert result.hour == 8
        assert result.day == 5

    def test_next_active_time_during_active_hours(self):
        dt = datetime(2026, 5, 4, 14, 0)
        result = next_active_time(dt)
        assert result == dt
