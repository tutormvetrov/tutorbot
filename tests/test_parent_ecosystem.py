import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from handlers.users.callbacks import (
    process_parent_child_homework,
    process_parent_child_homework_detail,
    process_parent_child_homework_file,
    process_parent_child_payments,
    process_parent_child_schedule,
)
from handlers.users.screens import get_user_home_payload
from handlers.users.start import command_start, process_age, process_child_age, process_child_name, process_full_name
from tests.helpers import DummyBot, DummyCallbackQuery, DummyConn, DummyMessage, DummyPool, DummyState
from utils.ui_text import lesson_balance_label


def _keyboard_texts(reply_markup):
    return [button.text for row in reply_markup.inline_keyboard for button in row]


class RegistrationEntryPointTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_user_sees_role_picker_as_first_registration_step(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return None

        state = DummyState()
        message = DummyMessage(user_id=701, full_name="Новый Пользователь")

        await command_start(message, state, FakeDB())

        self.assertEqual(state.state.state, "Registration:waiting_for_role")
        self.assertIn("выберите вашу роль", message.answers[-1].lower())
        self.assertEqual(
            _keyboard_texts(message.reply_markups[-1]),
            ["🎓 Я ученик", "👥 Мы занимаемся вдвоём", "👨‍👩‍👧 Я родитель ученика"],
        )


class ParentRegistrationFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_parent_registration_creates_parent_profile_and_child_link(self):
        state = DummyState()
        await state.update_data(role="parent", reg_total=5)

        await process_full_name(DummyMessage("Мария Иванова", user_id=801), state)
        await process_age(DummyMessage("35", user_id=801), state)
        await process_child_name(DummyMessage("Анна Иванова", user_id=801), state)

        class FakeDB:
            def __init__(self):
                self.conn = DummyConn()
                self.pool = DummyPool(self.conn)
                self.link_calls = []

            async def find_active_student_by_name(self, full_name):
                self.link_calls.append(("find", full_name))
                return {"telegram_id": 555123, "full_name": full_name, "role": "student", "is_active": True}

            async def upsert_parent_student_link(self, parent_id, student_info, student_id=None):
                self.link_calls.append(("link", parent_id, student_info, student_id))
                return 1

        db = FakeDB()
        message = DummyMessage("12", user_id=801, full_name="Мария Иванова")

        await process_child_age(message, state, db)

        self.assertIsNone(state.state)
        self.assertTrue(db.conn.executed)
        self.assertIn("INSERT INTO users", db.conn.executed[0][0])
        self.assertIn("'parent'", db.conn.executed[0][0])
        self.assertEqual(
            db.link_calls,
            [
                ("find", "Анна Иванова"),
                ("link", 801, "Анна Иванова (12)", 555123),
            ],
        )
        self.assertIn("Связь с учеником найдена", message.answers[-1])
        self.assertEqual(
            _keyboard_texts(message.reply_markups[-1]),
            [
                "👨‍👩‍👧 Мои дети",
                "📁 Материалы",
                "📞 Контакты",
                "👤 Профиль",
                "✉️ Написать преподавателю",
            ],
        )


class ParentCabinetFlowTest(unittest.IsolatedAsyncioTestCase):
    def test_lesson_balance_label_uses_russian_plural_rules(self):
        self.assertEqual(lesson_balance_label(1), "1 урок")
        self.assertEqual(lesson_balance_label(2), "2 урока")
        self.assertEqual(lesson_balance_label(5), "5 уроков")
        self.assertEqual(lesson_balance_label(11), "11 уроков")
        self.assertEqual(lesson_balance_label(23), "23 урока")

    async def test_student_home_payload_shows_next_lesson_homework_and_balance(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Анна Иванова",
                    "role": "student",
                    "is_active": True,
                }

            async def get_active_lessons(self, telegram_id):
                return [{"lesson_date": datetime(2026, 4, 8, 16, 0)}]

            async def get_student_homework(self, telegram_id, status):
                return [{"id": 1}, {"id": 2}]

            async def get_student_lesson_balance(self, telegram_id):
                return 3

        text, keyboard = await get_user_home_payload(FakeDB(), 900)

        self.assertIn("Анна Иванова", text)
        self.assertIn("Ближайший урок", text)
        self.assertIn("Активные ДЗ: <b>2</b>", text)
        self.assertIn("🎓 Баланс: <b>3 урока</b>", text)
        self.assertIn("schedule", [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data])

    async def test_parent_home_payload_shows_child_summary(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Иванова",
                    "role": "parent",
                    "is_active": True,
                }

            async def get_parent_children_overview(self, parent_id):
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

        text, keyboard = await get_user_home_payload(FakeDB(), 901)

        self.assertIn("Кабинет родителя", text)
        self.assertIn("Анна Иванова", text)
        self.assertIn("Активные ДЗ: <b>2</b>", text)
        self.assertIn("🎓 Баланс: <b>3 урока</b>", text)
        self.assertIn("parent:child:7", [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data])

    async def test_parent_child_tabs_cover_schedule_homework_and_payments(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Иванова",
                    "role": "parent",
                    "is_active": True,
                }

            async def get_parent_child_link(self, parent_id, link_id):
                return {
                    "link_id": link_id,
                    "student_id": 707,
                    "child_label": "Анна Иванова",
                    "link_status": "linked",
                    "lesson_format": "online",
                    "next_lesson_date": datetime(2026, 4, 8, 16, 0),
                    "active_homework_count": 1,
                    "lesson_balance": 2,
                }

            async def get_parent_child_schedule(self, parent_id, link_id):
                return [
                    {"lesson_date": datetime(2026, 4, 8, 16, 0), "lesson_format": "online"},
                    {"lesson_date": datetime(2026, 4, 10, 16, 0), "lesson_format": "online"},
                ]

            async def get_parent_child_homework(self, parent_id, link_id, status="active"):
                return [
                    {
                        "id": 1,
                        "title": "Чтение текста",
                        "description": None,
                        "deadline": datetime(2026, 4, 9),
                        "attachment_file_id": "doc-1",
                    }
                ]

            async def get_homework_by_id(self, hw_id):
                return {
                    "id": hw_id,
                    "student_id": 707,
                    "status": "active",
                    "title": "Чтение текста",
                    "description": "Прочитать текст и выписать 10 слов.",
                    "deadline": datetime(2026, 4, 9),
                    "attachment_name": "task.pdf",
                    "attachment_mime_type": "application/pdf",
                    "attachment_file_id": "doc-1",
                }

            async def get_parent_child_payments(self, parent_id, link_id, limit=20):
                return [
                    {
                        "amount": 3000,
                        "lessons_count": 4,
                        "lessons_remaining": 2,
                        "payment_date": datetime(2026, 4, 1),
                    }
                ]

        db = FakeDB()

        schedule_message = DummyMessage(user_id=902, full_name="Мария Иванова")
        schedule_callback = DummyCallbackQuery(
            "parent:child:7:schedule",
            message=schedule_message,
            user_id=902,
            full_name="Мария Иванова",
        )
        await process_parent_child_schedule(schedule_callback, db)
        self.assertIn("Расписание", schedule_message.edits[-1])
        self.assertIn("08.04.2026", schedule_message.edits[-1])

        homework_message = DummyMessage(user_id=902, full_name="Мария Иванова")
        homework_callback = DummyCallbackQuery(
            "parent:child:7:homework:active",
            message=homework_message,
            user_id=902,
            full_name="Мария Иванова",
        )
        await process_parent_child_homework(homework_callback, db)
        self.assertIn("Активные задания", homework_message.edits[-1])
        self.assertIn("Чтение текста", homework_message.edits[-1])
        self.assertIn(
            "parent:child:7:homework:view:1:active",
            [button.callback_data for row in homework_message.reply_markups[-1].inline_keyboard for button in row if button.callback_data],
        )

        homework_detail_message = DummyMessage(user_id=902, full_name="Мария Иванова")
        homework_detail_callback = DummyCallbackQuery(
            "parent:child:7:homework:view:1:active",
            message=homework_detail_message,
            user_id=902,
            full_name="Мария Иванова",
        )
        await process_parent_child_homework_detail(homework_detail_callback, db)
        self.assertIn("Домашнее задание ребёнка", homework_detail_message.edits[-1])
        self.assertIn("Прочитать текст", homework_detail_message.edits[-1])

        bot = DummyBot()
        homework_file_message = DummyMessage(user_id=902, full_name="Мария Иванова", bot=bot)
        homework_file_callback = DummyCallbackQuery(
            "parent:child:7:homework:file:1:active",
            message=homework_file_message,
            user_id=902,
            full_name="Мария Иванова",
            bot=bot,
        )
        await process_parent_child_homework_file(homework_file_callback, db)
        self.assertEqual(len(bot.sent_documents), 1)
        self.assertEqual(bot.sent_documents[0].chat_id, 902)
        self.assertEqual(bot.sent_documents[0].document, "doc-1")

        payments_message = DummyMessage(user_id=902, full_name="Мария Иванова")
        payments_callback = DummyCallbackQuery(
            "parent:child:7:payments",
            message=payments_message,
            user_id=902,
            full_name="Мария Иванова",
        )
        await process_parent_child_payments(payments_callback, db)
        self.assertIn("Оплата", payments_message.edits[-1])
        self.assertIn("3000", payments_message.edits[-1])
