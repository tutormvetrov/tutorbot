import sys
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin_sections.health import _format_health_text
from handlers.users.admin_sections.homework import (
    admin_homework_edit_description_entered,
    admin_homework_edit_keep_deadline,
    admin_homework_edit_start,
    admin_homework_manage,
    admin_homework_send_now,
    admin_hw_deadline_entered,
)
from keyboards.inline import make_homework_manage_actions_keyboard
from tests.helpers import DummyBot, DummyCallbackQuery, DummyMessage, DummyState
from utils.db_api.schema import DatabaseSchemaMixin
from utils.scheduler import queued_homework_delivery_job
from utils.ui_text import build_admin_homework_list_text


class HomeworkDeliverySchemaTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_creates_queue_table_and_indexes(self):
        class FakeSchema(DatabaseSchemaMixin):
            def __init__(self):
                self.calls = []

            async def execute(self, query, *args, **kwargs):
                self.calls.append((query, args, kwargs))

        db = FakeSchema()
        await db.create_table_homework_delivery_queue()

        sql = "\n".join(call[0] for call in db.calls)
        self.assertIn("CREATE TABLE IF NOT EXISTS homework_delivery_queue", sql)
        self.assertIn("homework_id INTEGER NOT NULL UNIQUE REFERENCES homework(id) ON DELETE CASCADE", sql)
        self.assertIn("include_attachment BOOLEAN DEFAULT false", sql)
        self.assertIn("homework_delivery_queue_deliver_after_idx", sql)
        self.assertIn("homework_delivery_queue_student_after_idx", sql)


class HomeworkDeliveryAdminFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_night_create_queues_homework_and_exposes_send_now(self):
        state = DummyState()
        await state.update_data(
            student_id=555,
            title="",
            description="Ночное ДЗ",
            attachment=None,
            admin_return_view="admin:all_homework",
        )

        class FakeDB:
            def __init__(self):
                self.queued = []

            async def add_homework(self, student_id, title, description, deadline, attachment=None):
                self.add_call = (student_id, title, description, deadline, attachment)
                return 777

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def upsert_homework_delivery(self, homework_id, student_id, delivery_kind, deliver_after, include_attachment=False):
                self.queued.append((homework_id, student_id, delivery_kind, deliver_after, include_attachment))

        db = FakeDB()
        message = DummyMessage("11.04.2026", user_id=config.ADMIN_ID, bot=DummyBot())

        with patch("handlers.users.admin_sections.homework.business_now", return_value=datetime(2026, 4, 10, 2, 0)):
            await admin_hw_deadline_entered(message, state, db)

        self.assertEqual(len(db.queued), 1)
        self.assertEqual(db.queued[0][0:3], (777, 555, "new"))
        self.assertEqual(db.queued[0][3], datetime(2026, 4, 10, 10, 0))
        self.assertFalse(message.bot.sent_messages)
        self.assertIn("10.04.2026 10:00", message.answers[-1])
        callbacks = [button.callback_data for row in message.reply_markups[-1].inline_keyboard for button in row]
        self.assertIn("hw_send_now:777", callbacks)

    async def test_night_edit_queues_update_and_manage_card_shows_send_now(self):
        bot = DummyBot()
        state = DummyState()
        manage_message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=901, message_id=88)
        start_callback = DummyCallbackQuery(
            "hw_edit_start:78",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.update_calls = []
                self.queue_row = None
                self.homework = {
                    "id": 78,
                    "student_id": 555,
                    "full_name": "Иван Петров",
                    "title": "",
                    "description": "Старое ДЗ",
                    "attachment_file_id": "doc-file-id",
                    "attachment_file_unique_id": "doc-unique-id",
                    "attachment_name": "old.docx",
                    "attachment_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "deadline": datetime(2026, 4, 10),
                    "status": "active",
                    "queued_delivery_kind": None,
                    "queued_deliver_after": None,
                    "queued_include_attachment": False,
                    "queued_attempts": 0,
                    "queued_last_error": None,
                }

            async def get_homework_by_id(self, hw_id):
                return self.homework if hw_id == 78 else None

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def update_homework(self, homework_id, student_id, title, description, deadline, attachment=None):
                self.update_calls.append((homework_id, student_id, title, description, deadline, attachment))
                self.homework.update(
                    title=title,
                    description=description,
                    deadline=deadline,
                    attachment_file_id=(attachment or {}).get("file_id"),
                    attachment_file_unique_id=(attachment or {}).get("file_unique_id"),
                    attachment_name=(attachment or {}).get("file_name"),
                    attachment_mime_type=(attachment or {}).get("mime_type"),
                )

            async def upsert_homework_delivery(self, homework_id, student_id, delivery_kind, deliver_after, include_attachment=False):
                self.queue_row = {
                    "homework_id": homework_id,
                    "student_id": student_id,
                    "delivery_kind": delivery_kind,
                    "deliver_after": deliver_after,
                    "include_attachment": include_attachment,
                }
                self.homework.update(
                    queued_delivery_kind=delivery_kind,
                    queued_deliver_after=deliver_after,
                    queued_include_attachment=include_attachment,
                    queued_attempts=0,
                    queued_last_error=None,
                )

            async def get_all_active_homework(self):
                return [self.homework]

        db = FakeDB()
        await admin_homework_edit_start(start_callback, state, db)

        edit_message = DummyMessage("Новое ночное описание", user_id=config.ADMIN_ID, bot=bot)
        edit_message.entities = [object()]
        edit_message.html_text = edit_message.text
        await admin_homework_edit_description_entered(edit_message, state)

        keep_deadline_callback = DummyCallbackQuery(
            "hw_edit_keep_deadline",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        with patch("handlers.users.admin_sections.homework.business_now", return_value=datetime(2026, 4, 10, 1, 30)):
            await admin_homework_edit_keep_deadline(keep_deadline_callback, state, db)

        self.assertEqual(db.queue_row["delivery_kind"], "updated")
        self.assertEqual(db.queue_row["deliver_after"], datetime(2026, 4, 10, 10, 0))
        self.assertFalse(bot.sent_messages)
        self.assertIn("Обновление запланировано", manage_message.answers[-1])

        manage_callback = DummyCallbackQuery(
            "admin:homework_manage:78",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        await admin_homework_manage(manage_callback, db)
        callbacks = [button.callback_data for row in manage_message.reply_markups[-1].inline_keyboard for button in row]
        self.assertIn("hw_send_now:78", callbacks)

    async def test_send_now_sends_actual_homework_and_clears_queue(self):
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, bot=bot)
        callback = DummyCallbackQuery(
            "hw_send_now:77",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.cleared = []

            async def get_homework_by_id(self, hw_id):
                return {
                    "id": 77,
                    "student_id": 555,
                    "title": "",
                    "description": "Ночное ДЗ",
                    "attachment_file_id": "doc-file-id",
                    "attachment_name": "night.docx",
                    "attachment_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "deadline": datetime(2026, 4, 11),
                }

            async def get_homework_delivery(self, hw_id):
                return {
                    "homework_id": hw_id,
                    "delivery_kind": "new",
                    "include_attachment": True,
                }

            async def clear_homework_delivery(self, homework_id):
                self.cleared.append(homework_id)

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def mark_homework_delivery_failure(self, homework_id, attempted_at, error):
                raise AssertionError("mark_homework_delivery_failure should not be called")

        db = FakeDB()
        await admin_homework_send_now(callback, db)

        self.assertEqual(db.cleared, [77])
        self.assertEqual(bot.sent_documents[0].document, "doc-file-id")
        self.assertIn("Новое домашнее задание", bot.sent_messages[0].text)
        self.assertIn("Уведомление отправлено сейчас", message.edits[-1])


class HomeworkDeliverySchedulerTest(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_batches_multiple_items_for_same_student(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.cleared = []
                self.failed = []

            async def get_due_homework_deliveries(self, due_before, retry_before):
                return [
                    {
                        "id": 1,
                        "student_id": 555,
                        "title": "",
                        "description": "Новое ДЗ",
                        "attachment_name": None,
                        "attachment_mime_type": None,
                        "deadline": datetime(2026, 4, 11),
                        "delivery_kind": "new",
                        "include_attachment": False,
                    },
                    {
                        "id": 2,
                        "student_id": 555,
                        "title": "",
                        "description": "Обновлённое ДЗ",
                        "attachment_name": "night.pdf",
                        "attachment_mime_type": "application/pdf",
                        "deadline": datetime(2026, 4, 12),
                        "delivery_kind": "updated",
                        "include_attachment": True,
                    },
                ]

            async def clear_homework_delivery(self, homework_id):
                self.cleared.append(homework_id)

            async def mark_homework_delivery_failure(self, homework_id, attempted_at, error):
                self.failed.append((homework_id, error))

        db = FakeDB()
        await queued_homework_delivery_job(bot, db)

        self.assertEqual(db.cleared, [1, 2])
        self.assertEqual(db.failed, [])
        self.assertEqual(len(bot.sent_messages), 1)
        self.assertEqual(len(bot.sent_documents), 0)
        self.assertIn("Утренний пакет домашних заданий", bot.sent_messages[0].text)
        self.assertIn("Новые ДЗ", bot.sent_messages[0].text)
        self.assertIn("Обновлённые ДЗ", bot.sent_messages[0].text)
        self.assertEqual(
            bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data,
            "reply:homework",
        )

    async def test_scheduler_single_item_preserves_single_delivery_behavior(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.cleared = []

            async def get_due_homework_deliveries(self, due_before, retry_before):
                return [
                    {
                        "id": 9,
                        "student_id": 555,
                        "title": "",
                        "description": "Одно ДЗ",
                        "attachment_file_id": "file-id",
                        "attachment_name": "one.pdf",
                        "attachment_mime_type": "application/pdf",
                        "deadline": datetime(2026, 4, 11),
                        "delivery_kind": "new",
                        "include_attachment": True,
                    }
                ]

            async def clear_homework_delivery(self, homework_id):
                self.cleared.append(homework_id)

            async def mark_homework_delivery_failure(self, homework_id, attempted_at, error):
                raise AssertionError("mark_homework_delivery_failure should not be called")

        db = FakeDB()
        await queued_homework_delivery_job(bot, db)

        self.assertEqual(db.cleared, [9])
        self.assertEqual(len(bot.sent_documents), 1)
        self.assertEqual(bot.sent_documents[0].document, "file-id")
        self.assertEqual(
            bot.sent_messages[0].reply_markup.inline_keyboard[0][0].callback_data,
            "reply:homework:9",
        )

    async def test_scheduler_marks_failure_and_keeps_queue(self):
        class FailingBot(DummyBot):
            async def send_message(self, chat_id, text, reply_markup=None):
                raise RuntimeError("telegram down")

        bot = FailingBot()

        class FakeDB:
            def __init__(self):
                self.cleared = []
                self.failed = []

            async def get_due_homework_deliveries(self, due_before, retry_before):
                return [
                    {
                        "id": 5,
                        "student_id": 555,
                        "title": "",
                        "description": "Сломанное ДЗ",
                        "deadline": datetime(2026, 4, 11),
                        "delivery_kind": "new",
                        "include_attachment": False,
                    }
                ]

            async def clear_homework_delivery(self, homework_id):
                self.cleared.append(homework_id)

            async def mark_homework_delivery_failure(self, homework_id, attempted_at, error):
                self.failed.append((homework_id, error))

        db = FakeDB()
        await queued_homework_delivery_job(bot, db)

        self.assertEqual(db.cleared, [])
        self.assertEqual(len(db.failed), 1)
        self.assertEqual(db.failed[0][0], 5)
        self.assertIn("telegram down", db.failed[0][1])


class HomeworkDeliveryUiTest(unittest.TestCase):
    def test_admin_homework_list_shows_queue_badge(self):
        text = build_admin_homework_list_text(
            [
                {
                    "full_name": "Наталья Пименова",
                    "title": "",
                    "description": "Тестовое ДЗ",
                    "deadline": datetime(2026, 4, 11),
                    "queued_deliver_after": datetime(2026, 4, 10, 10, 0),
                }
            ]
        )
        self.assertIn("На 10.04.2026 10:00", text)

    def test_manage_keyboard_shows_send_now_when_item_is_queued(self):
        kb = make_homework_manage_actions_keyboard(77, can_send_now=True)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("hw_send_now:77", callbacks)

    def test_health_text_includes_queued_homework_metrics(self):
        text = _format_health_text(
            7,
            {"synced_at_local": "01.04.2026 12:00", "imported": 3, "updated": 1, "deleted": 0, "skipped": 2},
            {
                "status": "running",
                "scheduler": "running",
                "jobs": {
                    "queued_homework_delivery": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:10:00+00:00",
                        "sent_students": 2,
                        "sent_items": 3,
                        "failed_items": 0,
                        "due_items": 3,
                    }
                },
            },
            [],
        )

        self.assertIn("Отложенная домашка", text)
        self.assertIn("учеников=2", text)
        self.assertIn("заданий=3", text)
        self.assertIn("в очереди=3", text)


if __name__ == "__main__":
    unittest.main()
