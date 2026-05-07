import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin import (
    admin_preview_parents,
    admin_preview_parent_from_student_selected,
    admin_preview_parent_selected,
    admin_preview_stop,
    admin_preview_student_selected,
)
from handlers.users.callbacks import (
    back_to_menu,
    process_homework,
    process_homework_done,
    process_parent_child_homework,
    process_parent_child_payments,
    process_parent_child_schedule,
)
from tests.helpers import DummyCallbackQuery, DummyMessage, DummyState
from utils.preview_mode import PREVIEW_BLOCKED_ALERT, PREVIEW_STATE_FILE, get_admin_preview_session


def _keyboard_texts(reply_markup):
    return [button.text for row in reply_markup.inline_keyboard for button in row]


class FakePreviewDB:
    def __init__(self, admin_id: int):
        self.admin_id = admin_id
        self.homework_done_calls = []

    async def get_user(self, telegram_id):
        users = {
            self.admin_id: {
                "telegram_id": self.admin_id,
                "full_name": "Admin",
                "role": "teacher_admin",
                "is_active": True,
            },
            201: {
                "telegram_id": 201,
                "full_name": "Нина Долгова",
                "role": "student",
                "is_active": True,
                "lesson_format": "online",
                "lesson_reminders": "enabled",
            },
            301: {
                "telegram_id": 301,
                "full_name": "Мария Иванова",
                "role": "parent",
                "is_active": True,
            },
        }
        return users.get(telegram_id)

    async def get_student_homework(self, user_id, status):
        if user_id == 201 and status == "active":
            return [
                {
                    "id": 42,
                    "title": "Чтение текста",
                    "description": "Прочитать страницу 15",
                    "deadline": datetime(2026, 4, 9),
                }
            ]
        return []

    async def get_parent_children_overview(self, parent_id):
        if parent_id != 301:
            return []
        return [
            {
                "link_id": 7,
                "child_label": "Анна Иванова",
                "link_status": "linked",
                "next_lesson_date": datetime(2026, 4, 8, 16, 0),
                "active_homework_count": 2,
                "lesson_balance": 3,
            }
        ]

    async def get_parents_overview(self):
        return []

    async def get_students_overview(self):
        return [
            {
                "telegram_id": 201,
                "full_name": "Нина Долгова",
                "lesson_format": "online",
                "lesson_balance": 3,
                "next_lesson_date": datetime(2026, 4, 8, 16, 0),
            }
        ]

    async def get_parent_child_link(self, parent_id, link_id):
        if parent_id != 301 or link_id != 7:
            return None
        return {
            "link_id": link_id,
            "child_label": "Анна Иванова",
            "link_status": "linked",
            "lesson_format": "online",
            "next_lesson_date": datetime(2026, 4, 8, 16, 0),
            "active_homework_count": 2,
            "lesson_balance": 3,
        }

    async def get_parent_child_schedule(self, parent_id, link_id):
        if parent_id != 301 or link_id != 7:
            return []
        return [
            {"lesson_date": datetime(2026, 4, 8, 16, 0), "lesson_format": "online"},
            {"lesson_date": datetime(2026, 4, 10, 16, 0), "lesson_format": "online"},
        ]

    async def get_student_lesson_balance(self, user_id):
        return 3 if user_id == 201 else 0

    async def get_active_lessons(self, user_id):
        if user_id == 201:
            return [{"lesson_date": datetime(2026, 4, 8, 16, 0), "lesson_format": "online"}]
        return []

    async def get_student_payments(self, user_id, limit=5):
        if user_id != 201:
            return []
        return [
            {
                "created_at": datetime(2026, 4, 7, 12, 0),
                "payment_date": datetime(2026, 4, 7, 12, 0),
                "amount": 4500,
                "lessons_count": 4,
                "lessons_remaining": 3,
                "comment": "Апрель",
            }
        ]

    async def get_admin_dashboard_snapshot(self):
        return {
            "active_students": 1,
            "lessons_today": 0,
            "unpaid_students": 0,
            "students_without_upcoming_lessons": 0,
            "pending_freezes": 0,
            "active_homework": 1,
        }

    async def get_student_transactions(self, student_id, limit=15):
        if student_id == 201:
            return [
                {
                    "type": "payment_added",
                    "amount_lessons": 4,
                    "created_at": datetime(2026, 4, 7, 12, 0),
                    "payment_amount": 4500,
                }
            ]
        return []

    async def mark_homework_done(self, hw_id, user_id):
        self.homework_done_calls.append((hw_id, user_id))


class AdminPreviewModeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.admin_id_backup = config.ADMIN_ID
        self.admin_id = config.ADMIN_ID or 990001
        config.ADMIN_ID = self.admin_id

        self.preview_backup = PREVIEW_STATE_FILE.read_text(encoding="utf-8") if PREVIEW_STATE_FILE.exists() else None
        PREVIEW_STATE_FILE.unlink(missing_ok=True)

    def tearDown(self):
        config.ADMIN_ID = self.admin_id_backup
        if self.preview_backup is None:
            PREVIEW_STATE_FILE.unlink(missing_ok=True)
        else:
            PREVIEW_STATE_FILE.write_text(self.preview_backup, encoding="utf-8")

    async def test_admin_can_open_student_preview_and_use_student_navigation(self):
        db = FakePreviewDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_preview_student_selected(
            DummyCallbackQuery(
                "admin:student_pick_select:preview_student:201:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )

        self.assertIn("Режим preview", message.edits[-1])
        self.assertIn("Нина Долгова", message.edits[-1])
        self.assertIn("🛑 Выйти из preview", _keyboard_texts(message.reply_markups[-1]))

        await process_homework(
            DummyCallbackQuery("homework", message=message, user_id=self.admin_id, full_name="Admin"),
            db,
        )
        self.assertIn("Активные задания", message.edits[-1])
        self.assertIn("Прочитать страницу 15", message.edits[-1])
        self.assertIn("Режим preview", message.edits[-1])

        await back_to_menu(
            DummyCallbackQuery("back_to_menu", message=message, user_id=self.admin_id, full_name="Admin"),
            DummyState(),
            db,
        )
        self.assertIn("Главное меню", message.edits[-1])
        self.assertIn("Нина Долгова", message.edits[-1])

    async def test_admin_can_open_parent_preview_and_child_schedule(self):
        db = FakePreviewDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_preview_parent_selected(
            DummyCallbackQuery(
                "admin:parent_preview_select:301:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )

        self.assertIn("Кабинет родителя", message.edits[-1])
        self.assertIn("Мария Иванова", message.edits[-1])
        self.assertIn("Анна Иванова", message.edits[-1])

        await process_parent_child_schedule(
            DummyCallbackQuery(
                "parent:child:7:schedule",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertIn("Расписание", message.edits[-1])
        self.assertIn("08.04.2026", message.edits[-1])
        self.assertIn("Режим preview", message.edits[-1])

    async def test_admin_can_open_parent_preview_without_real_parents(self):
        db = FakePreviewDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_preview_parents(
            DummyCallbackQuery(
                "admin:preview:parents",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertIn("Просмотр как родитель", message.edits[-1])
        self.assertNotIn("Нет зарегистрированных родителей", message.edits[-1])
        self.assertIn("Нина Долгова", _keyboard_texts(message.reply_markups[-1])[0])

        await admin_preview_parent_from_student_selected(
            DummyCallbackQuery(
                "admin:student_pick_select:preview_parent:201:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )

        self.assertIn("Кабинет родителя", message.edits[-1])
        self.assertIn("Родитель ученика Нина Долгова", message.edits[-1])
        self.assertIn("Нина Долгова", message.edits[-1])

        await process_parent_child_schedule(
            DummyCallbackQuery(
                "parent:child:201:schedule",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertIn("Расписание", message.edits[-1])
        self.assertIn("08.04.2026", message.edits[-1])
        self.assertIn("Режим preview", message.edits[-1])

        await process_parent_child_homework(
            DummyCallbackQuery(
                "parent:child:201:homework:active",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertIn("Активные задания", message.edits[-1])
        self.assertIn("Прочитать страницу 15", message.edits[-1])

        await process_parent_child_payments(
            DummyCallbackQuery(
                "parent:child:201:payments",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertIn("Оплата", message.edits[-1])
        self.assertIn("4500 ₽", message.edits[-1])

    async def test_preview_stop_returns_to_admin_panel(self):
        db = FakePreviewDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_preview_student_selected(
            DummyCallbackQuery(
                "admin:student_pick_select:preview_student:201:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertIsNotNone(get_admin_preview_session(self.admin_id))

        await admin_preview_stop(
            DummyCallbackQuery("admin:preview:stop", message=message, user_id=self.admin_id, full_name="Admin"),
            DummyState(),
            db,
        )

        self.assertIsNone(get_admin_preview_session(self.admin_id))
        self.assertIn("Панель администратора", message.edits[-1])

    async def test_preview_blocks_write_actions(self):
        db = FakePreviewDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_preview_student_selected(
            DummyCallbackQuery(
                "admin:student_pick_select:preview_student:201:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )

        callback = DummyCallbackQuery("hw_done:42", message=message, user_id=self.admin_id, full_name="Admin")
        await process_homework_done(callback, db)

        self.assertEqual(callback.answers[-1].text, PREVIEW_BLOCKED_ALERT)
        self.assertTrue(callback.answers[-1].show_alert)
        self.assertEqual(db.homework_done_calls, [])


if __name__ == "__main__":
    unittest.main()
