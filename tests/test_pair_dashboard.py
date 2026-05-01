"""Tests for Stage В1: pair dashboard, shared goal text, weekly report."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.ui_text import (
    build_pair_invite_goal_inherit_text,
    build_pair_weekly_report_text,
    build_student_home_text,
)


class PairHomeTextTest(unittest.TestCase):
    def _user(self):
        return {"full_name": "Иван", "language": "Английский", "level": "B1"}

    def test_pair_with_goal_renders_goal_line(self):
        pair = {"title": "Иван и Мария", "shared_goal_text": "пройти B2 до января"}
        text = build_student_home_text(self._user(), 4, 1, pair=pair)
        self.assertIn("Наша цель", text)
        self.assertIn("пройти B2 до января", text)
        self.assertNotIn("ещё не задана", text)

    def test_pair_without_goal_shows_cta_line(self):
        pair = {"title": "Иван и Мария"}
        text = build_student_home_text(self._user(), 4, 1, pair=pair)
        self.assertIn("Общая цель ещё не задана", text)


class PairWeeklyReportTest(unittest.TestCase):
    def test_basic_stats_render(self):
        text = build_pair_weekly_report_text({
            "lessons_completed": 3,
            "homework_done": 5,
            "next_lesson_at": datetime(2026, 5, 5, 18, 0),
            "shared_goal_text": "пройти A2",
            "member_telegram_ids": [1, 2],
        })
        self.assertIn("Уроков завершено", text)
        self.assertIn("3", text)
        self.assertIn("ДЗ закрыто", text)
        self.assertIn("5", text)
        self.assertIn("пройти A2", text)

    def test_no_goal_omits_goal_line(self):
        text = build_pair_weekly_report_text({
            "lessons_completed": 1,
            "homework_done": 0,
            "next_lesson_at": None,
            "shared_goal_text": None,
            "member_telegram_ids": [1],
        })
        self.assertNotIn("Цель в фокусе", text)


class PairInviteInheritTextTest(unittest.TestCase):
    def test_partner_name_and_goal_appear(self):
        text = build_pair_invite_goal_inherit_text("Иван", "учусь для работы")
        self.assertIn("Иван", text)
        self.assertIn("учусь для работы", text)
        self.assertIn("Поддержать", text)


if __name__ == "__main__":
    unittest.main()
