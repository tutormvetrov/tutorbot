"""Tests for achievements, progress text, lesson feedback, and touch engine changes."""
import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.achievements import (
    ACHIEVEMENTS,
    ACHIEVEMENT_BY_KEY,
    ACHIEVEMENT_COUNT,
    LESSON_MILESTONES,
    build_achievement_congrats,
    build_admin_progress_text,
    build_progress_text,
    compute_next_milestone,
)
from utils.touch_engine import (
    parse_teacher_comment,
    select_touch_type,
    render_touch_message,
    should_send_touch,
    reload_templates,
)


# ── Achievement definitions ────────────────────────────────────────────────


class AchievementDefinitionsTest(unittest.TestCase):
    def test_achievement_count_matches_list(self):
        self.assertEqual(ACHIEVEMENT_COUNT, len(ACHIEVEMENTS))
        self.assertEqual(ACHIEVEMENT_COUNT, 12)

    def test_all_keys_unique(self):
        keys = [a["key"] for a in ACHIEVEMENTS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_by_key_lookup(self):
        self.assertIn("first_lesson", ACHIEVEMENT_BY_KEY)
        self.assertIn("lessons_50", ACHIEVEMENT_BY_KEY)
        self.assertEqual(ACHIEVEMENT_BY_KEY["streak_4"]["name"], "Марафонец")

    def test_lesson_milestones(self):
        self.assertEqual(LESSON_MILESTONES, [5, 10, 25, 50])


# ── Achievement check lambdas ──────────────────────────────────────────────


class AchievementCheckTest(unittest.TestCase):
    def _metrics(self, **overrides):
        base = {
            "total_lessons": 0,
            "streak_weeks": 0,
            "tenure_weeks": 0,
            "goal_text": None,
            "plan_total": 0,
            "plan_done": 0,
            "hw_perfect_months": 0,
        }
        base.update(overrides)
        return base

    def test_first_lesson_unlocked_at_1(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["first_lesson"]["check"](self._metrics(total_lessons=1)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["first_lesson"]["check"](self._metrics(total_lessons=0)))

    def test_lessons_5(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["lessons_5"]["check"](self._metrics(total_lessons=5)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["lessons_5"]["check"](self._metrics(total_lessons=4)))

    def test_lessons_50(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["lessons_50"]["check"](self._metrics(total_lessons=50)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["lessons_50"]["check"](self._metrics(total_lessons=49)))

    def test_streak_4(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["streak_4"]["check"](self._metrics(streak_weeks=4)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["streak_4"]["check"](self._metrics(streak_weeks=3)))

    def test_streak_12(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["streak_12"]["check"](self._metrics(streak_weeks=12)))

    def test_hw_perfect_month(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["hw_perfect_month"]["check"](self._metrics(hw_perfect_months=1)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["hw_perfect_month"]["check"](self._metrics(hw_perfect_months=0)))

    def test_plan_complete(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["plan_complete"]["check"](self._metrics(plan_total=5, plan_done=5)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["plan_complete"]["check"](self._metrics(plan_total=5, plan_done=4)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["plan_complete"]["check"](self._metrics(plan_total=0, plan_done=0)))

    def test_tenure_26w(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["tenure_26w"]["check"](self._metrics(tenure_weeks=26)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["tenure_26w"]["check"](self._metrics(tenure_weeks=25)))

    def test_goal_set(self):
        self.assertTrue(ACHIEVEMENT_BY_KEY["goal_set"]["check"](self._metrics(goal_text="Сдать IELTS")))
        self.assertFalse(ACHIEVEMENT_BY_KEY["goal_set"]["check"](self._metrics(goal_text=None)))
        self.assertFalse(ACHIEVEMENT_BY_KEY["goal_set"]["check"](self._metrics(goal_text="")))


# ── Congrats text ──────────────────────────────────────────────────────────


class CongratsTextTest(unittest.TestCase):
    def test_congrats_contains_name(self):
        text = build_achievement_congrats("first_lesson", "informal")
        self.assertIn("Первый шаг", text)
        self.assertIn("Новое достижение", text)

    def test_congrats_formal(self):
        text = build_achievement_congrats("lessons_5", "formal")
        self.assertIn("отличный темп", text)

    def test_congrats_schoolchild(self):
        text = build_achievement_congrats("lessons_50", "schoolchild")
        self.assertIn("монстр", text)

    def test_unknown_key_returns_empty(self):
        self.assertEqual(build_achievement_congrats("nonexistent"), "")


# ── Progress text ──────────────────────────────────────────────────────────


class ProgressTextTest(unittest.TestCase):
    def _progress(self, **overrides):
        base = {
            "total_lessons": 15,
            "lessons_this_month": 4,
            "first_lesson_date": datetime.now() - timedelta(days=90),
            "last_lesson_date": datetime.now() - timedelta(days=2),
            "hw_total": 3,
            "hw_done": 2,
            "plan_total": 5,
            "plan_done": 3,
            "achievement_count": 4,
        }
        base.update(overrides)
        return base

    def test_basic_progress_text(self):
        text = build_progress_text(self._progress(), [], streak_weeks=5)
        self.assertIn("15", text)
        self.assertIn("5 недель подряд", text)
        self.assertIn("Достижения (0 / 12)", text)

    def test_progress_pair_title(self):
        text = build_progress_text(
            self._progress(), [], streak_weeks=0,
            is_pair=True, pair_title="Иван + Мария",
        )
        self.assertIn("Иван + Мария", text)

    def test_progress_formal(self):
        text = build_progress_text(
            self._progress(), [], streak_weeks=0,
            speech_style="formal",
        )
        self.assertIn("Ваш прогресс", text)

    def test_progress_informal(self):
        text = build_progress_text(
            self._progress(), [], streak_weeks=0,
            speech_style="informal",
        )
        self.assertIn("Твой прогресс", text)

    def test_unlocked_achievements_shown(self):
        achievements = [
            {"achievement_key": "first_lesson", "unlocked_at": datetime.now()},
            {"achievement_key": "lessons_5", "unlocked_at": datetime.now()},
        ]
        text = build_progress_text(self._progress(), achievements, streak_weeks=0)
        self.assertIn("Достижения (2 / 12)", text)
        self.assertIn("Первый шаг ✅", text)
        self.assertIn("Пятёрка ✅", text)


# ── Admin progress text ────────────────────────────────────────────────────


class AdminProgressTextTest(unittest.TestCase):
    def test_basic_admin_progress(self):
        progress = {
            "total_lessons": 20,
            "lessons_this_month": 5,
            "hw_total": 3,
            "hw_done": 2,
            "plan_total": 0,
            "plan_done": 0,
        }
        text = build_admin_progress_text(progress, [{"key": "a"}, {"key": "b"}], streak_weeks=4)
        self.assertIn("20", text)
        self.assertIn("4 нед.", text)
        self.assertIn("2/12", text)

    def test_feedback_in_admin_text(self):
        progress = {"total_lessons": 10, "lessons_this_month": 3, "hw_total": 0, "hw_done": 0, "plan_total": 0, "plan_done": 0}
        feedback = [
            {"rating": "great"},
            {"rating": "great"},
            {"rating": "hard"},
        ]
        text = build_admin_progress_text(progress, [], streak_weeks=0, feedback=feedback)
        self.assertIn("×2", text)
        self.assertIn("×1", text)


# ── Next milestone ─────────────────────────────────────────────────────────


class NextMilestoneTest(unittest.TestCase):
    def test_within_3_of_milestone(self):
        self.assertIsNotNone(compute_next_milestone(23))
        self.assertIn("25", compute_next_milestone(23))

    def test_exactly_at_milestone(self):
        self.assertIsNone(compute_next_milestone(25))

    def test_far_from_milestone(self):
        self.assertIsNone(compute_next_milestone(15))

    def test_close_to_50(self):
        result = compute_next_milestone(48)
        self.assertIsNotNone(result)
        self.assertIn("50", result)


# ── Touch engine: select_touch_type ────────────────────────────────────────


class SelectTouchTypeTest(unittest.TestCase):
    def test_zero_balance_returns_none(self):
        result = select_touch_type(
            {"topic": "math"}, has_active_hw=False,
            streak_weeks=5, balance=0,
        )
        self.assertIsNone(result)

    def test_difficulty_returns_support(self):
        result = select_touch_type(
            {"difficulty": "глаголы"}, has_active_hw=False,
            streak_weeks=0, balance=3,
        )
        self.assertEqual(result, "support")

    def test_topic_returns_progress(self):
        result = select_touch_type(
            {"topic": "артикли"}, has_active_hw=False,
            streak_weeks=0, balance=3,
        )
        self.assertEqual(result, "progress")

    def test_active_hw_returns_hw_nudge(self):
        result = select_touch_type(
            {}, has_active_hw=True,
            streak_weeks=0, balance=3,
        )
        self.assertEqual(result, "hw_nudge")

    def test_streak_returns_motivation(self):
        result = select_touch_type(
            {}, has_active_hw=False,
            streak_weeks=4, balance=3,
        )
        self.assertEqual(result, "motivation")

    def test_goal_reminder(self):
        result = select_touch_type(
            {}, has_active_hw=False,
            streak_weeks=0, balance=3,
            goal_text="IELTS", last_goal_reminder_days=20,
        )
        self.assertEqual(result, "goal_reminder")

    def test_goal_reminder_too_recent(self):
        result = select_touch_type(
            {}, has_active_hw=False,
            streak_weeks=0, balance=3,
            goal_text="IELTS", last_goal_reminder_days=5,
        )
        self.assertIsNone(result)

    def test_milestone_approaching(self):
        result = select_touch_type(
            {}, has_active_hw=False,
            streak_weeks=0, balance=3,
            total_lessons=23,
        )
        self.assertEqual(result, "milestone_approaching")

    def test_milestone_approaching_has_highest_priority(self):
        result = select_touch_type(
            {"topic": "math", "difficulty": "hard"},
            has_active_hw=True,
            streak_weeks=5, balance=3,
            total_lessons=48,
        )
        self.assertEqual(result, "milestone_approaching")


# ── Touch engine: parse_teacher_comment ────────────────────────────────────


class ParseTeacherCommentTest(unittest.TestCase):
    def test_empty_returns_none_fields(self):
        result = parse_teacher_comment(None)
        self.assertIsNone(result["topic"])
        self.assertIsNone(result["difficulty"])
        self.assertIsNone(result["task"])

    def test_short_comment_ignored(self):
        result = parse_teacher_comment("Ок")
        self.assertIsNone(result["topic"])

    def test_topic_extraction(self):
        result = parse_teacher_comment("Разобрали Present Perfect. Хорошо пошло.")
        self.assertIn("Present Perfect", result["topic"])

    def test_difficulty_extraction(self):
        result = parse_teacher_comment("Сложно далось условное наклонение. Надо повторить.")
        self.assertIn("условное наклонение", result["difficulty"])

    def test_task_extraction(self):
        result = parse_teacher_comment("Задание: повторить неправильные глаголы. Тема прошла ок.")
        self.assertIn("повторить неправильные глаголы", result["task"])

    def test_raw_first_sentence(self):
        result = parse_teacher_comment("Работали над произношением. Делаем упражнения.")
        self.assertIsNotNone(result["raw_first_sentence"])
        self.assertIn("произношением", result["raw_first_sentence"])


# ── Touch engine: render_touch_message ─────────────────────────────────────


class RenderTouchMessageTest(unittest.TestCase):
    def setUp(self):
        self._templates = {
            "progress": {
                "warm": {
                    "informal": ["{name}, на прошлом уроке разобрали {topic} — молодец!"],
                    "formal": ["{name}, на прошлом занятии мы разобрали {topic} — хорошая работа!"],
                }
            },
            "motivation": {
                "warm": {
                    "informal": ["{name}, уже {streak} недель подряд без перерывов!"],
                }
            },
            "milestone_approaching": {
                "warm": {
                    "informal": ["{name}, до {next_milestone_text} — почти!"],
                }
            },
        }

    def test_render_basic(self):
        with patch("utils.touch_engine._load_templates", return_value=self._templates):
            msg, idx = render_touch_message(
                "progress", "Иван",
                {"topic": "артикли"},
                brand_tone="warm", speech_style="informal",
            )
            self.assertIn("Иван", msg)
            self.assertIn("артикли", msg)
            self.assertIsNotNone(idx)

    def test_render_formal(self):
        with patch("utils.touch_engine._load_templates", return_value=self._templates):
            msg, idx = render_touch_message(
                "progress", "Анна",
                {"topic": "глаголы"},
                brand_tone="warm", speech_style="formal",
            )
            self.assertIn("Анна", msg)
            self.assertIn("занятии", msg)

    def test_render_empty_templates(self):
        with patch("utils.touch_engine._load_templates", return_value={}):
            msg, idx = render_touch_message("progress", "Тест", {})
            self.assertIsNone(msg)
            self.assertIsNone(idx)

    def test_render_milestone(self):
        with patch("utils.touch_engine._load_templates", return_value=self._templates):
            msg, idx = render_touch_message(
                "milestone_approaching", "Иван",
                {"next_milestone_text": "25-го урока осталось 2"},
                brand_tone="warm", speech_style="informal",
            )
            self.assertIn("25-го", msg)

    def test_dedup_template_index(self):
        multi = {
            "progress": {
                "warm": {
                    "informal": ["Шаблон 0", "Шаблон 1", "Шаблон 2"],
                }
            },
        }
        with patch("utils.touch_engine._load_templates", return_value=multi):
            _, idx = render_touch_message(
                "progress", "Тест", {},
                brand_tone="warm", speech_style="informal",
                last_template_index=1,
            )
            self.assertNotEqual(idx, 1)


# ── Touch engine: should_send_touch ────────────────────────────────────────


class ShouldSendTouchTest(unittest.TestCase):
    def _recent(self, count: int) -> list:
        # Spread synthetic past sends across the last week (NOT today).
        base = datetime.now() - timedelta(days=2)
        return [
            {"sent_at": base - timedelta(hours=i * 6), "template_type": "progress", "template_index": 0}
            for i in range(count)
        ]

    def test_too_many_touches(self):
        now = datetime.now()
        self.assertFalse(should_send_touch(
            now - timedelta(days=2), now + timedelta(days=2),
            self._recent(2), now.date(), balance=5,
        ))

    def test_zero_balance(self):
        now = datetime.now()
        self.assertFalse(should_send_touch(
            now - timedelta(days=2), now + timedelta(days=2),
            [], now.date(), balance=0,
        ))

    def test_no_last_lesson(self):
        now = datetime.now()
        self.assertFalse(should_send_touch(
            None, now + timedelta(days=2),
            [], now.date(), balance=5,
        ))

    def test_lesson_today_skipped(self):
        now = datetime.now()
        self.assertFalse(should_send_touch(
            now, now + timedelta(days=3),
            [], now.date(), balance=5,
        ))

    def test_valid_send_window(self):
        now = datetime.now()
        self.assertTrue(should_send_touch(
            now - timedelta(days=2), now + timedelta(days=3),
            [], now.date(), balance=5,
        ))


# ── Admin Today: hard feedback in snapshot ─────────────────────────────────


class AdminTodayHardFeedbackTest(unittest.TestCase):
    def test_hard_feedback_in_today_text(self):
        from utils.ui_text import build_admin_today_text
        snapshot = {
            "lessons_today": [],
            "unpaid_count": 0,
            "missing_homework_count": 0,
            "pending_freeze_count": 0,
            "unanswered_replies_count": 0,
            "hard_feedback": [
                {"full_name": "Иван", "date": "05.05"},
            ],
        }
        text = build_admin_today_text(snapshot, datetime.now().date())
        self.assertIn("Сложный урок", text)
        self.assertIn("Иван", text)

    def test_no_hard_feedback(self):
        from utils.ui_text import build_admin_today_text
        snapshot = {
            "lessons_today": [],
            "unpaid_count": 0,
            "missing_homework_count": 0,
            "pending_freeze_count": 0,
            "unanswered_replies_count": 0,
            "hard_feedback": [],
        }
        text = build_admin_today_text(snapshot, datetime.now().date())
        self.assertNotIn("Сложный урок", text)
        self.assertIn("Всё в порядке", text)


# ── Keyboards: parent child progress button ────────────────────────────────


class ParentChildProgressButtonTest(unittest.TestCase):
    def test_parent_child_keyboard_has_progress(self):
        from keyboards.inline import make_parent_child_keyboard
        kb = make_parent_child_keyboard(42, linked=True, engagement_mode="active")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("parent:child:42:progress", callbacks)

    def test_parent_child_keyboard_trust_has_progress(self):
        from keyboards.inline import make_parent_child_keyboard
        kb = make_parent_child_keyboard(42, linked=True, engagement_mode="trust")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("parent:child:42:progress", callbacks)

    def test_parent_child_keyboard_unlinked_no_progress(self):
        from keyboards.inline import make_parent_child_keyboard
        kb = make_parent_child_keyboard(42, linked=False)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertNotIn("parent:child:42:progress", callbacks)


# ── Keyboards: feedback keyboard ───────────────────────────────────────────


class FeedbackKeyboardTest(unittest.TestCase):
    def test_feedback_keyboard_has_3_buttons(self):
        from keyboards.inline import make_lesson_feedback_keyboard
        kb = make_lesson_feedback_keyboard(123, "informal")
        buttons = kb.inline_keyboard[0]
        self.assertEqual(len(buttons), 3)
        callbacks = [b.callback_data for b in buttons]
        self.assertIn("lesson_feedback:123:great", callbacks)
        self.assertIn("lesson_feedback:123:ok", callbacks)
        self.assertIn("lesson_feedback:123:hard", callbacks)

    def test_feedback_keyboard_formal_labels(self):
        from keyboards.inline import make_lesson_feedback_keyboard
        kb = make_lesson_feedback_keyboard(1, "formal")
        labels = [b.text for b in kb.inline_keyboard[0]]
        self.assertTrue(any("Было сложно" in l for l in labels))

    def test_feedback_keyboard_schoolchild_labels(self):
        from keyboards.inline import make_lesson_feedback_keyboard
        kb = make_lesson_feedback_keyboard(1, "schoolchild")
        labels = [b.text for b in kb.inline_keyboard[0]]
        self.assertTrue(any("Супер" in l for l in labels))


# ── Admin student card progress block ──────────────────────────────────────


class AdminStudentCardProgressTest(unittest.TestCase):
    def test_card_with_progress_block(self):
        from utils.ui_text import build_admin_student_card_text
        student = {
            "full_name": "Иван Петров",
            "telegram_id": 123,
            "lesson_reminders": "enabled",
            "cached_first_lesson_date": None,
            "first_lesson_date": None,
            "student_stage_override": None,
            "lessons_completed_count": 10,
            "lesson_format": "online",
            "speech_style": "informal",
            "student_type": "adult",
            "language": "English",
            "level": "B1",
            "lesson_duration_minutes": 60,
            "pricing_rate_id": None,
            "goal_text": None,
        }
        text = build_admin_student_card_text(
            student, balance=5, next_lesson=None,
            progress_block="📊 Прогресс\n📅 Уроков: 10",
        )
        self.assertIn("Прогресс", text)
        self.assertIn("Уроков: 10", text)

    def test_card_without_progress_block(self):
        from utils.ui_text import build_admin_student_card_text
        student = {
            "full_name": "Мария",
            "telegram_id": 456,
            "lesson_reminders": "enabled",
            "cached_first_lesson_date": None,
            "first_lesson_date": None,
            "student_stage_override": None,
            "lessons_completed_count": 0,
            "lesson_format": "online",
            "speech_style": "formal",
            "student_type": "adult",
            "language": "English",
            "level": "A1",
            "lesson_duration_minutes": 90,
            "pricing_rate_id": None,
            "goal_text": None,
        }
        text = build_admin_student_card_text(
            student, balance=0, next_lesson=None,
        )
        self.assertNotIn("Прогресс", text)


if __name__ == "__main__":
    unittest.main()
