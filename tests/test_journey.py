"""Tests for onboarding v2 journey: schedule generation, ui templates, progress."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.db_api.journey import (
    INITIAL_JOURNEY_KINDS,
    JOURNEY_KIND_FEEDBACK_AFTER_FIRST,
    JOURNEY_KIND_GOAL_PROMPT,
    JOURNEY_KIND_MATERIALS_INTRO,
    JOURNEY_KIND_WEEKLY_CHECKIN,
    _initial_schedule,
)
from utils.ui_text import (
    build_feedback_after_first_message,
    build_goal_prompt_message,
    build_journey_progress_text,
    build_materials_intro_message,
    build_prep_first_lesson_message,
    build_student_home_text,
    build_weekly_checkin_message,
)


class JourneyScheduleTest(unittest.TestCase):
    def test_initial_schedule_covers_four_kinds(self):
        registered = datetime(2026, 5, 1, 14, 0, 0)
        schedule = _initial_schedule(registered)
        self.assertEqual(set(schedule.keys()), set(INITIAL_JOURNEY_KINDS))
        self.assertEqual(set(INITIAL_JOURNEY_KINDS), {
            JOURNEY_KIND_GOAL_PROMPT,
            JOURNEY_KIND_MATERIALS_INTRO,
            JOURNEY_KIND_FEEDBACK_AFTER_FIRST,
            JOURNEY_KIND_WEEKLY_CHECKIN,
        })

    def test_goal_prompt_within_two_hours(self):
        registered = datetime(2026, 5, 1, 14, 0, 0)
        sched = _initial_schedule(registered)
        delta = sched[JOURNEY_KIND_GOAL_PROMPT] - registered
        self.assertEqual(delta, timedelta(hours=1))

    def test_materials_intro_at_10am_next_day(self):
        registered = datetime(2026, 5, 1, 14, 0, 0)
        sched = _initial_schedule(registered)
        self.assertEqual(sched[JOURNEY_KIND_MATERIALS_INTRO].hour, 10)
        self.assertEqual(sched[JOURNEY_KIND_MATERIALS_INTRO].date(), (registered + timedelta(days=1)).date())

    def test_weekly_checkin_at_d_plus_7_noon(self):
        registered = datetime(2026, 5, 1, 14, 0, 0)
        sched = _initial_schedule(registered)
        self.assertEqual(sched[JOURNEY_KIND_WEEKLY_CHECKIN].hour, 12)
        delta_days = (sched[JOURNEY_KIND_WEEKLY_CHECKIN].date() - registered.date()).days
        self.assertEqual(delta_days, 7)


class JourneyMessagesTest(unittest.TestCase):
    def test_goal_prompt_changes_with_brand_tone(self):
        warm = build_goal_prompt_message("warm")
        strict = build_goal_prompt_message("strict")
        self.assertNotEqual(warm, strict)
        self.assertIn("цел", warm.lower())
        self.assertIn("цел", strict.lower())

    def test_messages_contain_relevant_keywords(self):
        self.assertIn("материал", build_materials_intro_message("neutral").lower())
        self.assertIn("первый урок", build_prep_first_lesson_message("neutral").lower())
        self.assertIn("первый урок", build_feedback_after_first_message("neutral").lower())
        self.assertIn("неделя", build_weekly_checkin_message("neutral", has_goal=False).lower())
        self.assertIn("неделя", build_weekly_checkin_message("neutral", has_goal=True).lower())


class JourneyProgressTest(unittest.TestCase):
    def test_progress_renders_done_and_pending(self):
        text = build_journey_progress_text({
            "level_test": True,
            "goal": False,
            "materials": True,
            "first_lesson": False,
            "completed": False,
            "registered_at": datetime.now(),
        })
        self.assertIn("✅", text)
        self.assertIn("⬜", text)
        self.assertIn("Тест уровня", text)
        self.assertIn("Цель", text)


class JourneyHomeIntegrationTest(unittest.TestCase):
    def _user(self):
        return {"full_name": "Иван", "language": "Английский", "level": "A2"}

    def test_progress_hidden_when_completed(self):
        user = self._user()
        progress = {
            "level_test": True,
            "goal": True,
            "materials": True,
            "first_lesson": True,
            "completed": True,
            "registered_at": datetime.now(),
        }
        text = build_student_home_text(user, balance=2, active_homework_count=0, journey_progress=progress)
        self.assertNotIn("Прогресс:", text)

    def test_progress_hidden_after_14_days(self):
        user = self._user()
        progress = {
            "level_test": True,
            "goal": False,
            "materials": False,
            "first_lesson": False,
            "completed": False,
            "registered_at": datetime.now() - timedelta(days=20),
        }
        text = build_student_home_text(user, balance=2, active_homework_count=0, journey_progress=progress)
        self.assertNotIn("Прогресс:", text)

    def test_progress_shown_for_fresh_user(self):
        user = self._user()
        progress = {
            "level_test": True,
            "goal": False,
            "materials": False,
            "first_lesson": False,
            "completed": False,
            "registered_at": datetime.now() - timedelta(days=2),
        }
        text = build_student_home_text(user, balance=2, active_homework_count=0, journey_progress=progress)
        self.assertIn("Прогресс:", text)


class JourneyNavigationTest(unittest.TestCase):
    def test_student_more_menu_has_goal_entry(self):
        from keyboards.user import student_more_keyboard

        callbacks = [
            button.callback_data
            for row in student_more_keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("goal:set", callbacks)


if __name__ == "__main__":
    unittest.main()
