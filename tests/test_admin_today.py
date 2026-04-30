"""
Tests for Stage 2: «🎯 Сегодня» dashboard — mixin, text builder, and keyboard.
"""

import asyncio
import sys
import unittest
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from keyboards.inline import make_admin_today_keyboard
from utils.ui_text import build_admin_today_text


# ─── Fake DB for testing get_admin_today_snapshot ────────────────────────────

class FakeDB:
    """Minimal fake that satisfies DatabaseAdminTodayMixin dependencies."""

    def __init__(
        self,
        lessons_in_window=None,
        students_with_balances=None,
        lessons_missing_homework=None,
        pending_freeze_lessons=None,
        users_by_ids=None,
    ):
        self._lessons_in_window = lessons_in_window or []
        self._students_with_balances = students_with_balances or []
        self._lessons_missing_homework = lessons_missing_homework or []
        self._pending_freeze_lessons = pending_freeze_lessons or []
        self._users_by_ids = users_by_ids or []

    async def get_lessons_in_window(self, start_dt, end_dt):
        return self._lessons_in_window

    async def get_students_with_balances(self):
        return self._students_with_balances

    async def get_lessons_missing_homework(self):
        return self._lessons_missing_homework

    async def get_pending_freeze_lessons(self):
        return self._pending_freeze_lessons

    async def _get_users_by_ids(self, ids):
        return [u for u in self._users_by_ids if u["telegram_id"] in ids]

    # Paste the mixin method in so we don't need a real Pool
    async def get_admin_today_snapshot(self, today_start, tomorrow_start):
        import asyncio as _asyncio

        lessons_raw, students_with_balances, missing_hw, pending_freezes = await _asyncio.gather(
            self.get_lessons_in_window(today_start, tomorrow_start),
            self.get_students_with_balances(),
            self.get_lessons_missing_homework(),
            self.get_pending_freeze_lessons(),
        )

        student_ids = [row["student_id"] for row in (lessons_raw or [])]
        name_map: dict[int, str] = {}
        format_map: dict[int, str] = {}
        if student_ids:
            rows = await self._get_users_by_ids(student_ids)
            for row in rows:
                tid = row["telegram_id"]
                name_map[tid] = row.get("full_name") or str(tid)
                format_map[tid] = (row.get("lesson_format") or "online").strip().lower()

        lessons_today = []
        for row in (lessons_raw or []):
            lesson_date = row.get("lesson_date")
            sid = row["student_id"]
            lessons_today.append({
                "time": lesson_date.strftime("%H:%M") if lesson_date else "—",
                "full_name": name_map.get(sid, str(sid)),
                "lesson_format": format_map.get(sid, "online"),
            })

        unpaid_count = sum(
            1 for s in (students_with_balances or []) if int(s.get("lesson_balance") or 0) == 0
        )

        return {
            "lessons_today": lessons_today,
            "unpaid_count": unpaid_count,
            "missing_homework_count": len(missing_hw or []),
            "pending_freeze_count": len(pending_freezes or []),
            "unanswered_replies_count": 0,
        }


def run(coro):
    return asyncio.run(coro)


# ─── Tests ────────────────────────────────────────────────────────────────────

class AdminTodaySnapshotTest(unittest.TestCase):
    def test_empty_db_returns_zeroes(self):
        db = FakeDB()
        snapshot = run(db.get_admin_today_snapshot(
            datetime(2026, 5, 1, 0, 0),
            datetime(2026, 5, 2, 0, 0),
        ))
        self.assertEqual(snapshot["unpaid_count"], 0)
        self.assertEqual(snapshot["missing_homework_count"], 0)
        self.assertEqual(snapshot["pending_freeze_count"], 0)
        self.assertEqual(snapshot["unanswered_replies_count"], 0)
        self.assertEqual(snapshot["lessons_today"], [])

    def test_unpaid_count_is_students_with_zero_balance(self):
        db = FakeDB(students_with_balances=[
            {"telegram_id": 1, "full_name": "Анна", "lesson_balance": 0},
            {"telegram_id": 2, "full_name": "Борис", "lesson_balance": 3},
            {"telegram_id": 3, "full_name": "Вера", "lesson_balance": 0},
        ])
        snapshot = run(db.get_admin_today_snapshot(
            datetime(2026, 5, 1, 0, 0),
            datetime(2026, 5, 2, 0, 0),
        ))
        self.assertEqual(snapshot["unpaid_count"], 2)

    def test_lessons_today_includes_name_and_format(self):
        lesson_date = datetime(2026, 5, 1, 15, 30)
        db = FakeDB(
            lessons_in_window=[
                {"student_id": 101, "lesson_date": lesson_date, "status": "active"},
            ],
            users_by_ids=[
                {"telegram_id": 101, "full_name": "Мария Иванова", "lesson_format": "offline"},
            ],
        )
        snapshot = run(db.get_admin_today_snapshot(
            datetime(2026, 5, 1, 0, 0),
            datetime(2026, 5, 2, 0, 0),
        ))
        self.assertEqual(len(snapshot["lessons_today"]), 1)
        lesson = snapshot["lessons_today"][0]
        self.assertEqual(lesson["time"], "15:30")
        self.assertEqual(lesson["full_name"], "Мария Иванова")
        self.assertEqual(lesson["lesson_format"], "offline")

    def test_missing_homework_count_correct(self):
        db = FakeDB(lessons_missing_homework=[
            {"student_id": 1, "full_name": "X", "lesson_date": datetime(2026, 5, 2, 10, 0)},
            {"student_id": 2, "full_name": "Y", "lesson_date": datetime(2026, 5, 2, 14, 0)},
        ])
        snapshot = run(db.get_admin_today_snapshot(
            datetime(2026, 5, 1, 0, 0),
            datetime(2026, 5, 2, 0, 0),
        ))
        self.assertEqual(snapshot["missing_homework_count"], 2)

    def test_pending_freeze_count_correct(self):
        db = FakeDB(pending_freeze_lessons=[
            {"id": 1}, {"id": 2}, {"id": 3},
        ])
        snapshot = run(db.get_admin_today_snapshot(
            datetime(2026, 5, 1, 0, 0),
            datetime(2026, 5, 2, 0, 0),
        ))
        self.assertEqual(snapshot["pending_freeze_count"], 3)

    def test_unanswered_replies_count_is_zero_placeholder(self):
        db = FakeDB()
        snapshot = run(db.get_admin_today_snapshot(
            datetime(2026, 5, 1, 0, 0),
            datetime(2026, 5, 2, 0, 0),
        ))
        self.assertEqual(snapshot["unanswered_replies_count"], 0)


class AdminTodayTextTest(unittest.TestCase):
    def _make_snapshot(
        self,
        lessons=None,
        unpaid=0,
        missing_hw=0,
        pending_freeze=0,
        unanswered=0,
    ) -> dict:
        return {
            "lessons_today": lessons or [],
            "unpaid_count": unpaid,
            "missing_homework_count": missing_hw,
            "pending_freeze_count": pending_freeze,
            "unanswered_replies_count": unanswered,
        }

    def test_header_contains_date(self):
        snapshot = self._make_snapshot()
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("Сегодня", text)
        self.assertIn("2026", text)

    def test_no_lessons_shows_zero(self):
        snapshot = self._make_snapshot()
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("0", text)

    def test_lessons_are_listed(self):
        snapshot = self._make_snapshot(lessons=[
            {"time": "12:00", "full_name": "Иван Петров", "lesson_format": "online"},
            {"time": "15:30", "full_name": "Мария Вовк", "lesson_format": "offline"},
        ])
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("Иван Петров", text)
        self.assertIn("Мария Вовк", text)
        self.assertIn("12:00", text)
        self.assertIn("15:30", text)
        self.assertIn("онлайн", text)
        self.assertIn("очно", text)

    def test_online_offline_count_in_header(self):
        snapshot = self._make_snapshot(lessons=[
            {"time": "10:00", "full_name": "A", "lesson_format": "online"},
            {"time": "11:00", "full_name": "B", "lesson_format": "online"},
            {"time": "12:00", "full_name": "C", "lesson_format": "offline"},
        ])
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("2 онлайн", text)
        self.assertIn("1 очно", text)

    def test_attention_block_shows_unpaid(self):
        snapshot = self._make_snapshot(unpaid=2)
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("2", text)
        self.assertIn("оплат", text)

    def test_attention_block_shows_missing_hw(self):
        snapshot = self._make_snapshot(missing_hw=1)
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("ДЗ", text)

    def test_attention_block_shows_pending_freeze(self):
        snapshot = self._make_snapshot(pending_freeze=1)
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("заморозк", text)

    def test_all_clear_shows_ok_message(self):
        snapshot = self._make_snapshot()
        text = build_admin_today_text(snapshot, date(2026, 5, 1))
        self.assertIn("✅", text)


class AdminTodayKeyboardTest(unittest.TestCase):
    def _make_snapshot(self, pending_freeze=0):
        return {
            "lessons_today": [],
            "unpaid_count": 0,
            "missing_homework_count": 0,
            "pending_freeze_count": pending_freeze,
            "unanswered_replies_count": 0,
        }

    def _callbacks(self, snapshot):
        kb = make_admin_today_keyboard(snapshot)
        return [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

    def _texts(self, snapshot):
        kb = make_admin_today_keyboard(snapshot)
        return [button.text for row in kb.inline_keyboard for button in row]

    def test_exposes_lessons_callback(self):
        self.assertIn("admin:today:lessons", self._callbacks(self._make_snapshot()))

    def test_exposes_unpaid_callback(self):
        self.assertIn("admin:today:unpaid", self._callbacks(self._make_snapshot()))

    def test_exposes_missing_hw_callback(self):
        self.assertIn("admin:today:missing_hw", self._callbacks(self._make_snapshot()))

    def test_exposes_freezes_callback(self):
        self.assertIn("admin:freezes", self._callbacks(self._make_snapshot()))

    def test_exposes_inbox_callback(self):
        self.assertIn("admin:inbox", self._callbacks(self._make_snapshot()))

    def test_exposes_back_to_admin_callback(self):
        self.assertIn("admin:home", self._callbacks(self._make_snapshot()))

    def test_freeze_label_shows_count_when_nonzero(self):
        texts = self._texts(self._make_snapshot(pending_freeze=5))
        self.assertIn("❄️ Заявки на заморозку (5)", texts)

    def test_freeze_label_no_count_when_zero(self):
        texts = self._texts(self._make_snapshot(pending_freeze=0))
        self.assertIn("❄️ Заявки на заморозку", texts)
        self.assertNotIn("❄️ Заявки на заморозку (0)", texts)


if __name__ == "__main__":
    unittest.main()
