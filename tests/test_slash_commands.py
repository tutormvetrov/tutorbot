"""
Tests for Stage 4: slash-command shortcuts
(/today /freeze /plan /materials /health)
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data import config
from handlers.users.menu import (
    command_freeze,
    command_health,
    command_materials,
    command_plan,
    command_today,
)
from tests.helpers import DummyBot, DummyMessage


# ─── Minimal fake DB ──────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, *, user=None, role="student", balance=2, lessons=None, homework=None,
                 students=None, pending_freezes=None, today_snapshot=None, resources=None):
        self._user = user
        self._role = role
        self._balance = balance
        self._lessons = lessons if lessons is not None else []
        self._homework = homework if homework is not None else []
        self._students = students if students is not None else []
        self._pending_freezes = pending_freezes if pending_freezes is not None else []
        self._resources = resources if resources is not None else []
        self._today_snapshot = today_snapshot or {
            "lessons_today": [],
            "unpaid_count": 0,
            "missing_homework_count": 0,
            "pending_freeze_count": 0,
            "unanswered_replies_count": 0,
        }

    async def list_student_resources(self, student_id, *, include_global=True):
        return list(self._resources)

    async def list_global_resources(self):
        return [r for r in self._resources if r.get("student_id") is None]

    async def get_user(self, telegram_id):
        if self._user is None:
            return None
        return {"full_name": "Тест Тестов", "role": self._role, "is_active": True,
                "lesson_format": "online", "language": "ru", "level": "A2",
                "lesson_reminders": "enabled", **self._user}

    async def get_admin_today_snapshot(self, today_start, tomorrow_start):
        return self._today_snapshot

    async def get_active_lessons(self, student_id):
        return self._lessons

    async def get_student_homework(self, student_id, status):
        return self._homework

    async def get_student_lesson_balance(self, student_id):
        return self._balance

    async def get_active_learning_plan(self, student_id):
        return None

    async def ensure_study_plan_checklist(self, student_id):
        return {"lesson": None, "items": []}

    async def get_student_pair_for_student(self, student_id):
        return None

    async def get_pending_freeze_lessons(self):
        return self._pending_freezes

    async def get_all_students(self):
        return self._students

    async def get_parent_children_overview(self, parent_id):
        return []

    async def get_preview_context_for_admin(self, admin_id):
        return None

    async def get_preview_context(self, user_id):
        return None


# ─── /today ───────────────────────────────────────────────────────────────────

class TodayCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_sees_today_screen(self):
        snapshot = {
            "lessons_today": [],
            "unpaid_count": 1,
            "missing_homework_count": 0,
            "pending_freeze_count": 0,
            "unanswered_replies_count": 0,
        }
        db = FakeDB(today_snapshot=snapshot)
        msg = DummyMessage(user_id=config.ADMIN_ID)
        await command_today(msg, db)
        self.assertTrue(msg.answers, "Admin /today должен вызвать message.answer")
        combined = " ".join(msg.answers)
        self.assertTrue(
            "Сегодня" in combined or "🎯" in combined,
            f"Ожидался текст «Сегодня» или «🎯», получено: {combined[:200]}",
        )

    async def test_non_admin_sees_main_menu(self):
        db = FakeDB(user={"role": "student"})
        msg = DummyMessage(user_id=999)
        await command_today(msg, db)
        self.assertTrue(msg.answers, "Не-admin /today должен вызвать message.answer")


# ─── /freeze ──────────────────────────────────────────────────────────────────

class FreezeCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_with_active_lessons_sees_freeze_intro(self):
        from datetime import datetime
        lessons = [{"id": 1, "lesson_date": datetime(2026, 5, 10, 12, 0), "status": "active"}]
        db = FakeDB(user={"role": "student"}, lessons=lessons)
        msg = DummyMessage(user_id=42)
        await command_freeze(msg, db)
        self.assertTrue(msg.answers, "Студент с уроками должен получить freeze intro")
        combined = " ".join(msg.answers)
        self.assertTrue(
            "заморозк" in combined.lower() or "Заморозк" in combined,
            f"Ожидался текст о заморозке, получено: {combined[:200]}",
        )

    async def test_parent_sees_main_menu(self):
        db = FakeDB(user={"role": "parent"})
        msg = DummyMessage(user_id=43)
        await command_freeze(msg, db)
        self.assertTrue(msg.answers)

    async def test_student_without_lessons_sees_no_freeze_needed(self):
        db = FakeDB(user={"role": "student"}, lessons=[])
        msg = DummyMessage(user_id=44)
        await command_freeze(msg, db)
        self.assertTrue(msg.answers)
        combined = " ".join(msg.answers)
        self.assertIn("не нужна", combined)

    async def test_admin_sees_freeze_queue_empty(self):
        db = FakeDB(user={"role": "admin"}, pending_freezes=[])
        msg = DummyMessage(user_id=config.ADMIN_ID)
        await command_freeze(msg, db)
        self.assertTrue(msg.answers)


# ─── /plan ────────────────────────────────────────────────────────────────────

class PlanCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_sees_study_plan(self):
        db = FakeDB(user={"role": "student"})
        msg = DummyMessage(user_id=55)
        await command_plan(msg, db)
        self.assertTrue(msg.answers, "Студент должен получить учебный план")
        combined = " ".join(msg.answers)
        self.assertTrue(
            "план" in combined.lower() or "Учебный" in combined or "фокус" in combined.lower(),
            f"Ожидался текст учебного плана, получено: {combined[:200]}",
        )

    async def test_non_student_sees_main_menu(self):
        db = FakeDB(user={"role": "parent"})
        msg = DummyMessage(user_id=56)
        await command_plan(msg, db)
        self.assertTrue(msg.answers)

    async def test_unregistered_sees_main_menu(self):
        db = FakeDB(user=None)
        msg = DummyMessage(user_id=57)
        await command_plan(msg, db)
        self.assertTrue(msg.answers)


# ─── /materials ───────────────────────────────────────────────────────────────

class MaterialsCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_any_user_sees_materials(self):
        db = FakeDB(user=None)
        msg = DummyMessage(user_id=100)
        await command_materials(msg, db)
        self.assertTrue(msg.answers, "Команда /materials должна вызвать message.answer")

    async def test_materials_handler_responds(self):
        db = FakeDB(user=None)
        msg = DummyMessage(user_id=101)
        await command_materials(msg, db)
        self.assertEqual(len(msg.answers), 1)

    async def test_materials_for_student_uses_resources(self):
        resources = [
            {"id": 1, "student_id": 200, "label": "Курс", "url": "https://docs.google.com/x", "provider": "gdocs", "is_primary": True},
        ]
        db = FakeDB(user={"id": 200}, role="student", resources=resources)
        msg = DummyMessage(user_id=200)
        await command_materials(msg, db)
        self.assertEqual(len(msg.answers), 1)


# ─── /health ──────────────────────────────────────────────────────────────────

class HealthCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_no_response(self):
        db = FakeDB()
        msg = DummyMessage(user_id=999)
        await command_health(msg, db)
        self.assertFalse(msg.answers, "Не-admin /health не должен отвечать")

    async def test_admin_sees_health(self):
        db = FakeDB(students=[{"telegram_id": 1}, {"telegram_id": 2}])
        msg = DummyMessage(user_id=config.ADMIN_ID)
        await command_health(msg, db)
        self.assertTrue(msg.answers, "Админ /health должен получить ответ")
        combined = " ".join(msg.answers)
        self.assertTrue(
            "Здоровье" in combined or "health" in combined.lower(),
            f"Ожидался текст «Здоровье», получено: {combined[:200]}",
        )


if __name__ == "__main__":
    unittest.main()
