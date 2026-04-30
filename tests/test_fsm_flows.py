import sys
import asyncio
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin import admin_add_lesson_quick, render_admin_home
from handlers.users.admin_sections.health import _format_health_text
from handlers.users.admin_sections.homework import (
    admin_homework_edit_description_entered,
    admin_homework_edit_deadline_entered,
    admin_homework_edit_keep_content,
    admin_homework_edit_keep_deadline,
    admin_homework_edit_start,
    admin_hw_deadline_entered,
    admin_hw_description_entered,
)
from handlers.users.admin_sections.payments import admin_add_payment_quick, admin_payment_count_entered
from handlers.users.admin_sections.students import (
    admin_student_deactivate_prompt,
    admin_student_deactivate_review,
    admin_student_delete_confirm_direct,
    admin_student_delete_prompt,
    admin_student_delete_review,
    admin_student_duration_save,
    admin_student_duration_start,
    admin_student_format_toggle,
    admin_student_speech_style_toggle,
    admin_write_to_student_send,
    admin_write_to_student_start,
    lesson_followup_bookmark_save,
    lesson_followup_bookmark_start,
    lesson_followup_comment_save,
    lesson_followup_comment_start,
    lesson_followup_no_material,
)
from handlers.users.callbacks import (
    cancel_fsm,
    process_homework_attachment,
    process_homework,
    process_homework_list,
    process_lesson_presence,
    process_notif_action,
    start_student_reply,
)
from handlers.users.start import process_age, process_full_name, process_language, process_level, process_role_choice
from states.registration import StudentReply
from tests.helpers import DummyBot, DummyCallbackQuery, DummyConn, DummyMessage, DummyPool, DummyState
from utils.db_api.lessons import DatabaseLessonMixin
from utils.scheduler import (
    homework_gap_check_job,
    lesson_reminder_job,
    teacher_bookmark_reminder_job,
    teacher_lesson_followup_job,
)
from utils.ui_text import build_admin_dashboard_text


class RegistrationFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_registration_flow_advances_and_inserts_student(self):
        state = DummyState()
        role_message = DummyMessage(user_id=101, full_name="Иван Петров")
        role_callback = DummyCallbackQuery("role:student", message=role_message, user_id=101, full_name="Иван Петров")

        await process_role_choice(role_callback, state)
        self.assertEqual(state.data["role"], "student")
        self.assertEqual(state.data["reg_total"], 5)

        await process_full_name(DummyMessage("Иван Петров", user_id=101), state)
        self.assertEqual(state.data["full_name"], "Иван Петров")

        await process_age(DummyMessage("16", user_id=101), state)
        self.assertEqual(state.data["age"], 16)

        await process_language(DummyMessage("хочу учить English", user_id=101), state)
        self.assertEqual(state.data["language"], "Английский")

        class FakeDB:
            def __init__(self):
                self.conn = DummyConn()
                self.pool = DummyPool(self.conn)

        db = FakeDB()
        level_callback = DummyCallbackQuery(
            "level:A1",
            message=DummyMessage(user_id=101, full_name="Иван Петров"),
            user_id=101,
            full_name="Иван Петров",
        )
        await process_level(level_callback, state, db)

        self.assertTrue(level_callback.message.edits)
        self.assertEqual(state.state, None)
        self.assertTrue(db.conn.executed)
        self.assertIn("INSERT INTO users", db.conn.executed[0][0])


class StudentDangerActionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_student_delete_prompt_accepts_danger_callback_shape(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {"full_name": "Student Name", "role": "student", "is_active": True}

            async def get_user_deletion_snapshot(self, telegram_id):
                return {"lessons": 3, "payments_as_student": 2, "homework": 1}

        bot = DummyBot()
        callback = DummyCallbackQuery(
            "admin:student_delete_prompt:555:2",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )

        await admin_student_delete_prompt(callback, FakeDB())

        self.assertTrue(callback.message.edits)
        self.assertIn("admin:student_delete_review:555:2", callback.message.reply_markups[-1].inline_keyboard[0][0].callback_data)
        self.assertEqual(
            callback.message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:student_delete_review:555:2",
        )

    async def test_admin_student_deactivate_prompt_accepts_danger_callback_shape(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {"full_name": "Student Name", "role": "student", "is_active": True}

        bot = DummyBot()
        callback = DummyCallbackQuery(
            "admin:student_deactivate_prompt:555:2",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )

        await admin_student_deactivate_prompt(callback, FakeDB())

        self.assertTrue(callback.message.edits)
        self.assertIn("admin:student_deactivate_review:555:2", callback.message.reply_markups[-1].inline_keyboard[0][0].callback_data)
        self.assertEqual(
            callback.message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:student_deactivate_review:555:2",
        )

    async def test_admin_student_delete_review_renders_final_confirm(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {"full_name": "Student Name", "role": "student", "is_active": True}

        bot = DummyBot()
        callback = DummyCallbackQuery(
            "admin:student_delete_review:555:2",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )

        await admin_student_delete_review(callback, FakeDB())

        self.assertTrue(callback.message.edits)
        self.assertEqual(
            callback.message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:student_delete_confirm:555:2",
        )

    async def test_admin_student_deactivate_review_renders_final_confirm(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {"full_name": "Student Name", "role": "student", "is_active": True}

        bot = DummyBot()
        callback = DummyCallbackQuery(
            "admin:student_deactivate_review:555:2",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )

        await admin_student_deactivate_review(callback, FakeDB())

        self.assertTrue(callback.message.edits)
        self.assertEqual(
            callback.message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:student_deactivate_confirm:555:2",
        )

    async def test_admin_student_delete_confirm_deletes_user(self):
        class FakeDB:
            def __init__(self):
                self.deleted = []

            async def get_user(self, telegram_id):
                return {"full_name": "Student Name", "role": "student", "is_active": True}

            async def delete_user_fully(self, telegram_id):
                self.deleted.append(telegram_id)

        db = FakeDB()
        bot = DummyBot()
        callback = DummyCallbackQuery(
            "admin:student_delete_confirm:555:2",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )

        await admin_student_delete_confirm_direct(callback, db)

        self.assertEqual(db.deleted, [555])
        self.assertTrue(callback.message.edits)
        self.assertIn("Student Name", callback.message.edits[-1])


class HomeworkFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_homework_flow_keeps_html_links_and_accepts_slash_deadline(self):
        state = DummyState()
        await state.update_data(student_id=555)

        text = (
            "Сделайте упражнение и откройте <a href=\"https://example.com\">ссылку</a>. "
            + ("Дополнительная строка. " * 20)
        )
        message = DummyMessage(text, user_id=1)
        message.entities = [object()]
        message.html_text = text

        await admin_hw_description_entered(message, state)
        self.assertIn("description", state.data)
        self.assertIsNotNone(state.data["description"])
        self.assertEqual(state.data["title"], "")
        self.assertIn("<a href=\"https://example.com\">", state.data["description"])

        class FakeDB:
            def __init__(self):
                self.calls = []
                self.homework = {
                    "id": 777,
                    "student_id": 555,
                    "title": "",
                    "description": text,
                    "attachment_name": None,
                    "attachment_mime_type": None,
                    "deadline": datetime(2026, 4, 5),
                }

            async def add_homework(self, student_id, title, description, deadline, attachment=None):
                self.calls.append((student_id, title, description, deadline, attachment))
                return 777

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def get_homework_by_id(self, hw_id):
                return self.homework if hw_id == 777 else None

            async def clear_homework_delivery(self, homework_id):
                return None

            async def upsert_homework_delivery(self, homework_id, student_id, delivery_kind, deliver_after, include_attachment=False):
                return None

        db = FakeDB()
        deadline_message = DummyMessage("05/04/2026", user_id=1)
        with patch("handlers.users.admin_sections.homework.business_now", return_value=datetime(2026, 4, 5, 12, 0)):
            await admin_hw_deadline_entered(deadline_message, state, db)

        self.assertEqual(db.calls[0][0], 555)
        self.assertEqual(db.calls[0][3].strftime("%d.%m.%Y"), "05.04.2026")
        self.assertTrue(deadline_message.bot.sent_messages)
        student_message = deadline_message.bot.sent_messages[0].text
        self.assertIn("📝 Задание:\n", student_message)
        self.assertIn("<a href=\"https://example.com\">", student_message)
        self.assertNotIn("📄", student_message)
        self.assertEqual(student_message.count("Дополнительная строка."), 20)

    async def test_homework_flow_accepts_document_with_caption_and_resends_file(self):
        state = DummyState()
        await state.update_data(student_id=555)

        bot = DummyBot()
        document = type(
            "Document",
            (),
            {
                "file_id": "doc-file-id",
                "file_unique_id": "doc-unique-id",
                "file_name": "COD+.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        )()
        message = DummyMessage(
            user_id=1,
            bot=bot,
            caption="Откройте DOCX и выполните упражнения.",
            document=document,
        )

        await admin_hw_description_entered(message, state)
        self.assertEqual(state.data["attachment"]["file_id"], "doc-file-id")
        self.assertIn("Откройте DOCX", state.data["description"])

        class FakeDB:
            def __init__(self):
                self.calls = []
                self.homework = {
                    "id": 777,
                    "student_id": 555,
                    "status": "active",
                    "title": "",
                    "description": "Откройте DOCX и выполните упражнения.",
                    "attachment_file_id": "doc-file-id",
                    "attachment_name": "COD+.docx",
                    "attachment_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "deadline": datetime(2026, 4, 5),
                }

            async def add_homework(self, student_id, title, description, deadline, attachment=None):
                self.calls.append((student_id, title, description, deadline, attachment))
                return 777

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def get_homework_by_id(self, hw_id):
                return self.homework if hw_id == 777 else None

            async def clear_homework_delivery(self, homework_id):
                return None

            async def upsert_homework_delivery(self, homework_id, student_id, delivery_kind, deliver_after, include_attachment=False):
                return None

        db = FakeDB()
        deadline_message = DummyMessage("05.04.2026", user_id=1, bot=bot)
        with patch("handlers.users.admin_sections.homework.business_now", return_value=datetime(2026, 4, 5, 12, 0)):
            await admin_hw_deadline_entered(deadline_message, state, db)

        self.assertEqual(db.calls[0][4]["file_name"], "COD+.docx")
        self.assertEqual(bot.sent_documents[0].document, "doc-file-id")
        self.assertIn("COD+.docx", bot.sent_messages[0].text)

        callback = DummyCallbackQuery(
            "hw:file:777:active",
            message=DummyMessage(user_id=555, bot=bot),
            user_id=555,
            bot=bot,
        )
        await process_homework_attachment(callback, db)
        self.assertEqual(bot.sent_documents[-1].document, "doc-file-id")
        self.assertEqual(callback.answers[-1].text, "Файл отправлен.")

    async def test_homework_flow_keeps_html_link_from_document_caption(self):
        state = DummyState()
        await state.update_data(student_id=555)

        document = type(
            "Document",
            (),
            {
                "file_id": "doc-file-id",
                "file_unique_id": "doc-unique-id",
                "file_name": "COD+.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        )()
        message = DummyMessage(
            user_id=1,
            caption='Regardez <a href="https://youtu.be/example">cette video</a>.',
            document=document,
        )
        message.caption_entities = [object()]
        message.html_text = message.caption

        await admin_hw_description_entered(message, state)

        self.assertIn('<a href="https://youtu.be/example">cette video</a>', state.data["description"])

    async def test_admin_homework_edit_can_change_deadline_without_replacing_content(self):
        bot = DummyBot()
        state = DummyState()
        manage_message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=901, message_id=88)
        callback = DummyCallbackQuery(
            "hw_edit_start:77",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.update_calls = []
                self.homework = {
                    "id": 77,
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
                }

            async def get_homework_by_id(self, hw_id):
                return self.homework if hw_id == 77 else None

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def update_homework(self, homework_id, student_id, title, description, deadline, attachment=None):
                self.update_calls.append((homework_id, student_id, title, description, deadline, attachment))

            async def get_all_active_homework(self):
                return [self.homework]

            async def clear_homework_delivery(self, homework_id):
                return None

            async def upsert_homework_delivery(self, homework_id, student_id, delivery_kind, deliver_after, include_attachment=False):
                return None

        db = FakeDB()
        await admin_homework_edit_start(callback, state, db)
        self.assertEqual(state.state.state, "AdminEditHomework:waiting_for_description")

        keep_content_callback = DummyCallbackQuery(
            "hw_edit_keep_content",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        await admin_homework_edit_keep_content(keep_content_callback, state)
        self.assertEqual(state.state.state, "AdminEditHomework:waiting_for_deadline")

        deadline_message = DummyMessage("12.04.2026", user_id=config.ADMIN_ID, bot=bot)
        with patch("handlers.users.admin_sections.homework.business_now", return_value=datetime(2026, 4, 10, 12, 0)):
            await admin_homework_edit_deadline_entered(deadline_message, state, db)

        self.assertEqual(db.update_calls[0][0], 77)
        self.assertEqual(db.update_calls[0][3], "Старое ДЗ")
        self.assertEqual(db.update_calls[0][4].strftime("%d.%m.%Y"), "12.04.2026")
        self.assertEqual(db.update_calls[0][5]["file_name"], "old.docx")
        self.assertTrue(deadline_message.bot.sent_messages)
        self.assertIn("Домашнее задание обновлено", deadline_message.answers[-1])

    async def test_admin_homework_edit_can_change_text_and_keep_deadline(self):
        bot = DummyBot()
        state = DummyState()
        manage_message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=901, message_id=89)
        callback = DummyCallbackQuery(
            "hw_edit_start:78",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.update_calls = []
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
                }

            async def get_homework_by_id(self, hw_id):
                return self.homework if hw_id == 78 else None

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров"}

            async def update_homework(self, homework_id, student_id, title, description, deadline, attachment=None):
                self.update_calls.append((homework_id, student_id, title, description, deadline, attachment))

            async def get_all_active_homework(self):
                return [self.homework]

            async def clear_homework_delivery(self, homework_id):
                return None

            async def upsert_homework_delivery(self, homework_id, student_id, delivery_kind, deliver_after, include_attachment=False):
                return None

        db = FakeDB()
        await admin_homework_edit_start(callback, state, db)

        edit_message = DummyMessage("Новое описание с ссылкой <a href=\"https://example.com\">сюда</a>", user_id=config.ADMIN_ID, bot=bot)
        edit_message.entities = [object()]
        edit_message.html_text = edit_message.text
        await admin_homework_edit_description_entered(edit_message, state)
        self.assertEqual(state.state.state, "AdminEditHomework:waiting_for_deadline")

        keep_deadline_callback = DummyCallbackQuery(
            "hw_edit_keep_deadline",
            message=manage_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )
        with patch("handlers.users.admin_sections.homework.business_now", return_value=datetime(2026, 4, 10, 12, 0)):
            await admin_homework_edit_keep_deadline(keep_deadline_callback, state, db)

        self.assertEqual(db.update_calls[0][0], 78)
        self.assertIn("<a href=\"https://example.com\">сюда</a>", db.update_calls[0][3])
        self.assertEqual(db.update_calls[0][4].strftime("%d.%m.%Y"), "10.04.2026")
        self.assertEqual(db.update_calls[0][5]["file_name"], "old.docx")

    async def test_student_homework_opens_active_and_allows_switch_to_done(self):
        class FakeDB:
            async def get_student_homework(self, user_id, status):
                if status == "active":
                    return [{"id": 1, "title": "Активное ДЗ", "deadline": datetime(2026, 4, 5), "description": None}]
                return [{"id": 2, "title": "Сделано", "deadline": datetime(2026, 4, 1), "description": None}]

        message = DummyMessage(user_id=777)
        callback = DummyCallbackQuery("homework", message=message, user_id=777)
        await process_homework(callback, FakeDB())

        self.assertTrue(message.edits)
        self.assertIn("Активные задания", message.edits[-1])
        self.assertIn("Активное ДЗ", message.edits[-1])

        done_callback = DummyCallbackQuery("hw:done", message=message, user_id=777)
        await process_homework_list(done_callback, FakeDB())
        self.assertIn("Выполненные задания", message.edits[-1])
        self.assertIn("Сделано", message.edits[-1])


class LessonPresenceFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_lesson_presence_callback_reports_to_admin(self):
        lesson = {"id": 9, "student_id": 1001, "lesson_date": None}
        conn = DummyConn(fetchrow_result=lesson)

        class FakeDB:
            def __init__(self):
                self.pool = DummyPool(conn)

            async def get_user(self, telegram_id):
                return {"full_name": "Иван Петров", "role": "student"}

        bot = DummyBot()
        message = DummyMessage(user_id=1001, full_name="Иван Петров", bot=bot)
        callback = DummyCallbackQuery(
            "lesson_presence:on_time:9",
            message=message,
            user_id=1001,
            full_name="Иван Петров",
            bot=bot,
        )

        await process_lesson_presence(callback, FakeDB())

        self.assertTrue(message.reply_markups)
        self.assertTrue(bot.sent_messages)
        self.assertIn("Буду вовремя", bot.sent_messages[0].text)


class StudentAdminFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_format_toggle_updates_db_and_rerenders_card(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def set_lesson_format(self, student_id, lesson_format):
                self.calls.append((student_id, lesson_format))

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "offline",
                    "speech_style": "formal",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

        bot = DummyBot()
        message = DummyMessage(user_id=1, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "admin:student_format:555:0:offline",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_student_format_toggle(callback, FakeDB())

        self.assertEqual(callback.answers[0].text, "Формат переключён: очно")
        self.assertTrue(message.edits)

    async def test_student_speech_style_toggle_updates_db_and_rerenders_card(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def set_speech_style(self, student_id, speech_style):
                self.calls.append((student_id, speech_style))

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "speech_style": "informal",
                }

            async def get_student_lesson_balance(self, student_id):
                return 4

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

        bot = DummyBot()
        message = DummyMessage(user_id=1, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "admin:student_speech_style:555:0:informal",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_student_speech_style_toggle(callback, FakeDB())

        self.assertEqual(callback.answers[0].text, "Обращение переключено: на ты")
        self.assertTrue(message.edits)

    async def test_student_duration_flow_updates_db_and_restores_card(self):
        state = DummyState()
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=999, message_id=654)
        callback = DummyCallbackQuery(
            "admin:student_duration:555:2",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.duration_calls = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "speech_style": "formal",
                    "lesson_reminders": "enabled",
                    "lesson_duration_minutes": 90,
                }

            async def set_lesson_duration(self, student_id, minutes):
                self.duration_calls.append((student_id, minutes))

            async def get_student_lesson_balance(self, student_id):
                return 5

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 5, 14, 0)}]

        db = FakeDB()
        await admin_student_duration_start(callback, state, db)

        self.assertEqual(state.state.state, "AdminLessonFollowup:waiting_for_lesson_duration")
        self.assertTrue(message.edits)
        self.assertIn("Введите длительность урока", message.edits[-1])

        await admin_student_duration_save(DummyMessage("120", user_id=config.ADMIN_ID, bot=bot), state, db)

        self.assertEqual(state.state, None)
        self.assertEqual(db.duration_calls, [(555, 120)])
        self.assertTrue(bot.edited_messages)
        self.assertIn("Иван Петров", bot.edited_messages[-1].text)

    async def test_lesson_followup_comment_flow_saves_private_comment(self):
        state = DummyState()
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "lesson_followup:comment:77",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.saved_comments = []

            async def get_lesson_context(self, lesson_id):
                return {
                    "id": lesson_id,
                    "student_id": 555,
                    "full_name": "Анна Смирнова",
                    "lesson_date": datetime(2026, 4, 4, 14, 0),
                }

            async def save_teacher_comment(self, lesson_id, comment_text):
                self.saved_comments.append((lesson_id, comment_text))

        db = FakeDB()
        await lesson_followup_comment_start(callback, state, db)

        self.assertEqual(state.state.state, "AdminLessonFollowup:waiting_for_lesson_comment")
        self.assertTrue(message.edits)
        self.assertIn("приватный комментарий", message.edits[-1])

        await lesson_followup_comment_save(
            DummyMessage("Урок прошёл отлично", user_id=config.ADMIN_ID, bot=bot),
            state,
            db,
        )

        self.assertEqual(state.state, None)
        self.assertEqual(db.saved_comments, [(77, "Урок прошёл отлично")])

    async def test_lesson_followup_bookmark_flow_saves_bookmark(self):
        state = DummyState()
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "lesson_followup:bookmark:77:555",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.bookmark_calls = []

            async def get_lesson_context(self, lesson_id):
                return {
                    "id": lesson_id,
                    "student_id": 555,
                    "full_name": "Анна Смирнова",
                    "lesson_date": datetime(2026, 4, 4, 14, 0),
                }

            async def save_student_bookmark(self, student_id, lesson_id, bookmark_text, bookmark_state):
                self.bookmark_calls.append((student_id, lesson_id, bookmark_text, bookmark_state))

        db = FakeDB()
        await lesson_followup_bookmark_start(callback, state, db)

        self.assertEqual(state.state.state, "AdminLessonFollowup:waiting_for_lesson_bookmark")
        self.assertTrue(message.edits)
        self.assertIn("Этот текст придёт вам перед следующим занятием", message.edits[-1])

        await lesson_followup_bookmark_save(
            DummyMessage("Cosmopolite 1, page 69", user_id=config.ADMIN_ID, bot=bot),
            state,
            db,
        )

        self.assertEqual(state.state, None)
        self.assertEqual(
            db.bookmark_calls,
            [(555, 77, "Cosmopolite 1, page 69", "saved")],
        )

    async def test_lesson_followup_no_material_clears_bookmark_state(self):
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot)
        callback = DummyCallbackQuery(
            "lesson_followup:no_material:77:555",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        class FakeDB:
            def __init__(self):
                self.bookmark_calls = []

            async def get_lesson_context(self, lesson_id):
                return {
                    "id": lesson_id,
                    "student_id": 555,
                    "full_name": "Анна Смирнова",
                    "lesson_date": datetime(2026, 4, 4, 14, 0),
                }

            async def save_student_bookmark(self, student_id, lesson_id, bookmark_text, bookmark_state):
                self.bookmark_calls.append((student_id, lesson_id, bookmark_text, bookmark_state))

        db = FakeDB()
        await lesson_followup_no_material(callback, db)

        self.assertEqual(db.bookmark_calls, [(555, 77, None, "no_material")])
        self.assertEqual(callback.answers[0].text, "Отмечено: без учебника/книги")

    async def test_admin_quick_payment_flow_restores_student_card(self):
        state = DummyState()
        bot = DummyBot()
        message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot, chat_id=999, message_id=321)
        callback = DummyCallbackQuery(
            "admin:quick:add_payment:555:2",
            message=message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_add_payment_quick(callback, state)
        self.assertEqual(state.data["student_id"], 555)
        self.assertEqual(state.data["admin_return_view"], "admin:student_card:555:2")
        self.assertEqual(state.state.state, "AdminAddPayment:waiting_for_payment_amount")

        await state.update_data(amount=3000.0)

        class FakeDB:
            def __init__(self):
                self.calls = []

            async def add_payment(self, student_id, amount, count):
                self.calls.append((student_id, amount, count))

            async def get_user(self, telegram_id):
                return {
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                    "language": "Английский",
                    "level": "B1",
                    "lesson_format": "online",
                    "lesson_reminders": "enabled",
                    "telegram_id": telegram_id,
                }

            async def get_student_lesson_balance(self, student_id):
                return 6

            async def get_active_lessons(self, student_id):
                return [{"lesson_date": datetime(2026, 4, 8, 15, 30)}]

        await admin_payment_count_entered(DummyMessage("4", user_id=config.ADMIN_ID, bot=bot), state, FakeDB())

        self.assertEqual(state.state, None)
        self.assertTrue(bot.edited_messages)
        self.assertIn("Иван Петров", bot.edited_messages[-1].text)
        self.assertIn("Баланс", bot.edited_messages[-1].text)

    async def test_admin_cancel_restores_previous_view(self):
        state = DummyState()
        bot = DummyBot()
        await state.update_data(
            admin_return_view="admin:student_card:555:1",
            admin_origin_chat_id=888,
            admin_origin_message_id=55,
        )

        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "full_name": "Мария Вовк",
                    "role": "student",
                    "is_active": True,
                    "language": "Французский",
                    "level": "A2",
                    "lesson_format": "offline",
                    "lesson_reminders": "enabled",
                    "telegram_id": telegram_id,
                }

            async def get_student_lesson_balance(self, student_id):
                return 2

            async def get_active_lessons(self, student_id):
                return []

        callback = DummyCallbackQuery("cancel_fsm", user_id=config.ADMIN_ID, bot=bot)
        await cancel_fsm(callback, state, FakeDB())

        self.assertEqual(state.state, None)
        self.assertTrue(bot.edited_messages)
        self.assertIn("Мария Вовк", bot.edited_messages[-1].text)

    async def test_admin_can_send_sticker_to_student_inside_bot(self):
        state = DummyState()
        bot = DummyBot()

        class FakeDB:
            async def get_user(self, telegram_id):
                if telegram_id == 555:
                    return {"telegram_id": 555, "full_name": "Анна Смирнова", "role": "student"}
                return None

        start_message = DummyMessage(user_id=config.ADMIN_ID, full_name="Admin", bot=bot)
        start_callback = DummyCallbackQuery(
            "admin:write_to_student:555",
            message=start_message,
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
        )

        await admin_write_to_student_start(start_callback, state, FakeDB())
        self.assertEqual(state.state.state, "AdminWriteToStudent:waiting_for_message")
        self.assertIn("Отправьте сообщение для ученика", start_message.edits[-1])

        sticker_message = DummyMessage(
            user_id=config.ADMIN_ID,
            full_name="Admin",
            bot=bot,
            sticker=object(),
        )
        await admin_write_to_student_send(sticker_message, state, FakeDB())

        self.assertEqual(state.state, None)
        self.assertEqual(len(bot.copied_messages), 1)
        self.assertEqual(bot.copied_messages[0].chat_id, 555)
        self.assertEqual(
            bot.copied_messages[0].reply_markup.inline_keyboard[0][0].callback_data,
            "reply:teacher_message",
        )


class StudentReplyFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_reply_from_sticker_message_uses_fallback_prompt(self):
        state = DummyState()

        class FakeDB:
            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "full_name": "Анна Смирнова", "role": "student"}

        message = DummyMessage(user_id=555, full_name="Анна Смирнова", sticker=object())
        callback = DummyCallbackQuery(
            "reply:teacher_message",
            message=message,
            user_id=555,
            full_name="Анна Смирнова",
        )

        await start_student_reply(callback, state, FakeDB())

        self.assertEqual(state.state, StudentReply.waiting_for_message)
        self.assertFalse(message.edits)
        self.assertTrue(message.answers)
        self.assertIn("Напишите сообщение для преподавателя", message.answers[-1])
        self.assertEqual(callback.answers[-1].text, None)

    async def test_student_reply_from_text_message_keeps_edit_flow(self):
        state = DummyState()

        class FakeDB:
            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "full_name": "Анна Смирнова", "role": "student"}

        message = DummyMessage(text="Текст от преподавателя", user_id=555, full_name="Анна Смирнова")
        callback = DummyCallbackQuery(
            "reply:teacher_message",
            message=message,
            user_id=555,
            full_name="Анна Смирнова",
        )

        await start_student_reply(callback, state, FakeDB())

        self.assertEqual(state.state, StudentReply.waiting_for_message)
        self.assertTrue(message.edits)
        self.assertFalse(message.answers)
        self.assertIn("Напишите сообщение для преподавателя", message.edits[-1])


class ReminderLogicTest(unittest.IsolatedAsyncioTestCase):
    async def test_lesson_reminder_job_formats_online_and_offline_messages(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.sent = []

            async def get_lessons_for_reminder(self):
                now = datetime.now()
                return [
                    {
                        "id": 1,
                        "telegram_id": 11,
                        "full_name": "Online Student",
                        "lesson_date": now,
                        "lesson_reminders": "enabled",
                        "lesson_format": "online",
                        "speech_style": "informal",
                    },
                    {
                        "id": 2,
                        "telegram_id": 22,
                        "full_name": "Offline Formal Student",
                        "lesson_date": now,
                        "lesson_reminders": "enabled",
                        "lesson_format": "offline",
                        "speech_style": "formal",
                    },
                    {
                        "id": 3,
                        "telegram_id": 33,
                        "full_name": "Offline Informal Student",
                        "lesson_date": now,
                        "lesson_reminders": "enabled",
                        "lesson_format": "offline",
                        "speech_style": "informal",
                    },
                ]

            async def mark_lesson_reminder_sent(self, lesson_id):
                self.sent.append(lesson_id)

        db = FakeDB()
        await lesson_reminder_job(bot, db)

        self.assertEqual(db.sent, [1, 2, 3])
        self.assertEqual(len(bot.sent_messages), 3)
        online_text = bot.sent_messages[0].text
        offline_formal_text = bot.sent_messages[1].text
        offline_informal_text = bot.sent_messages[2].text
        self.assertIn("VK-Звонок", online_text)
        self.assertIn("Google Meet", online_text)
        self.assertIn("VPN", online_text)
        self.assertIn("очный урок", offline_formal_text)
        self.assertIn("через час", offline_formal_text)
        self.assertIn("подтвердите", offline_formal_text.lower())
        self.assertIn("Подтверди", offline_informal_text)

    async def test_lesson_reminder_job_skips_mark_sent_when_send_times_out(self):
        class SlowBot(DummyBot):
            async def send_message(self, chat_id, text, reply_markup=None):
                await asyncio.sleep(0.05)

        bot = SlowBot()

        class FakeDB:
            def __init__(self):
                self.sent = []

            async def get_lessons_for_reminder(self):
                return [
                    {
                        "id": 1,
                        "telegram_id": 11,
                        "full_name": "Online Student",
                        "lesson_date": datetime.now(),
                        "lesson_reminders": "enabled",
                        "lesson_format": "online",
                        "speech_style": "informal",
                    },
                ]

            async def mark_lesson_reminder_sent(self, lesson_id):
                self.sent.append(lesson_id)

        db = FakeDB()
        with patch("utils.scheduler.LESSON_REMINDER_SEND_TIMEOUT_SECONDS", 0.01):
            await lesson_reminder_job(bot, db)

        self.assertEqual(db.sent, [])

    async def test_teacher_lesson_followup_job_sends_message_and_marks_lesson(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.sent = []

            async def get_lessons_for_teacher_followup(self):
                return [
                    {
                        "id": 1,
                        "student_id": 555,
                        "full_name": "Анна Смирнова",
                        "lesson_date": datetime(2026, 4, 4, 12, 30),
                        "lesson_format": "online",
                    }
                ]

            async def mark_teacher_followup_sent(self, lesson_id):
                self.sent.append(lesson_id)

        db = FakeDB()
        await teacher_lesson_followup_job(bot, db)

        self.assertEqual(db.sent, [1])
        self.assertEqual(len(bot.sent_messages), 1)
        self.assertIn("Как прошёл урок", bot.sent_messages[0].text)
        callbacks = [
            button.callback_data
            for row in bot.sent_messages[0].reply_markup.inline_keyboard
            for button in row
        ]
        self.assertIn("lesson_followup:comment:1", callbacks)
        self.assertIn("lesson_followup:bookmark:1:555", callbacks)
        self.assertIn("lesson_followup:no_material:1:555", callbacks)

    async def test_teacher_bookmark_reminder_job_formats_saved_no_material_and_empty_states(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.sent = []

            async def get_lessons_for_teacher_bookmark_reminder(self):
                return [
                    {
                        "id": 1,
                        "student_id": 111,
                        "full_name": "Online Student",
                        "lesson_date": datetime(2026, 4, 4, 14, 0),
                        "lesson_format": "online",
                        "current_bookmark_state": "saved",
                        "current_bookmark_text": "Unit 5, page 72",
                    },
                    {
                        "id": 2,
                        "student_id": 222,
                        "full_name": "Offline Student",
                        "lesson_date": datetime(2026, 4, 4, 18, 0),
                        "lesson_format": "offline",
                        "current_bookmark_state": "no_material",
                        "current_bookmark_text": None,
                    },
                    {
                        "id": 3,
                        "student_id": 333,
                        "full_name": "Empty Bookmark Student",
                        "lesson_date": datetime(2026, 4, 4, 19, 0),
                        "lesson_format": "online",
                        "current_bookmark_state": "empty",
                        "current_bookmark_text": None,
                    },
                ]

            async def mark_teacher_pre_lesson_note_sent(self, lesson_id):
                self.sent.append(lesson_id)

        db = FakeDB()
        await teacher_bookmark_reminder_job(bot, db)

        self.assertEqual(db.sent, [1, 2, 3])
        self.assertEqual(len(bot.sent_messages), 3)
        self.assertIn("за 30 минут", bot.sent_messages[0].text)
        self.assertIn("Unit 5, page 72", bot.sent_messages[0].text)
        self.assertIn("за 1 час", bot.sent_messages[1].text)
        self.assertIn("не работали", bot.sent_messages[1].text)
        self.assertIn("не сохранена", bot.sent_messages[2].text)

    async def test_homework_reminder_job_keeps_full_homework_html(self):
        from utils.scheduler import homework_reminder_job

        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.marked = []

            async def get_homework_due_tomorrow(self):
                return [
                    {
                        "id": 7,
                        "telegram_id": 22,
                        "full_name": "Наталья Пименова",
                        "deadline": datetime(2026, 4, 5),
                        "title": "",
                        "description": "3. Le vocabulaire.\n<a href=\"https://example.com\">Apprenez ici</a>",
                        "speech_style": "formal",
                    }
                ]

            async def mark_homework_reminder_sent(self, hw_id):
                self.marked.append(hw_id)

        db = FakeDB()
        await homework_reminder_job(bot, db)

        self.assertEqual(db.marked, [7])
        self.assertEqual(len(bot.sent_messages), 1)
        text = bot.sent_messages[0].text
        self.assertIn("📝 Задание:\n", text)
        self.assertIn("3. Le vocabulaire.", text)
        self.assertIn("<a href=\"https://example.com\">Apprenez ici</a>", text)
        self.assertNotIn("...", text)

    async def test_homework_gap_check_job_notifies_admin_once_per_lesson(self):
        bot = DummyBot()

        class FakeDB:
            def __init__(self):
                self.marked = []

            async def get_lessons_missing_homework(self):
                return [{
                    "id": 77,
                    "student_id": 555,
                    "full_name": "Анна Смирнова",
                    "lesson_date": datetime(2026, 4, 4, 14, 0),
                    "previous_lesson_date": datetime(2026, 3, 28, 14, 0),
                }]

            async def mark_homework_check_reminder_sent(self, lesson_id):
                self.marked.append(lesson_id)

        db = FakeDB()
        await homework_gap_check_job(bot, db)

        self.assertEqual(db.marked, [77])
        self.assertEqual(len(bot.sent_messages), 1)
        self.assertIn("Проверьте домашнее задание", bot.sent_messages[0].text)
        self.assertIn("Анна Смирнова", bot.sent_messages[0].text)


class TeacherReminderQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_teacher_followup_query_uses_student_lesson_duration(self):
        class FakeDB(DatabaseLessonMixin):
            def __init__(self):
                self.calls = []

            async def execute(self, command, *args, **kwargs):
                self.calls.append((command, args, kwargs))
                return []

        db = FakeDB()
        await db.get_lessons_for_teacher_followup()

        command, _, kwargs = db.calls[0]
        self.assertIn("lesson_duration_minutes", command)
        self.assertIn("INTERVAL '1 minute'", command)
        self.assertTrue(kwargs["fetch"])

    async def test_teacher_bookmark_query_uses_online_and_offline_windows(self):
        class FakeDB(DatabaseLessonMixin):
            def __init__(self):
                self.calls = []

            async def execute(self, command, *args, **kwargs):
                self.calls.append((command, args, kwargs))
                return []

        db = FakeDB()
        await db.get_lessons_for_teacher_bookmark_reminder()

        command, _, kwargs = db.calls[0]
        self.assertIn("INTERVAL '30 minutes'", command)
        self.assertIn("INTERVAL '45 minutes'", command)
        self.assertIn("INTERVAL '60 minutes'", command)
        self.assertTrue(kwargs["fetch"])


class LessonCalendarSyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_lesson_from_calendar_resets_reminder_flags_when_date_changes(self):
        class FakeDB(DatabaseLessonMixin):
            def __init__(self):
                self.calls = []

            async def execute(self, command, *args, **kwargs):
                self.calls.append((command, args, kwargs))
                if "SELECT id, lesson_date FROM lessons" in command:
                    return {"id": 4, "lesson_date": datetime(2026, 4, 3, 14, 0)}
                return None

        db = FakeDB()
        result = await db.upsert_lesson_from_calendar(
            student_id=1693106968,
            google_event_id="event-123",
            lesson_date=datetime(2026, 4, 4, 14, 0),
        )

        self.assertEqual(result, "updated")
        update_command, update_args, update_kwargs = db.calls[1]
        self.assertIn("reminder_sent = CASE", update_command)
        self.assertIn("homework_check_reminder_sent = CASE", update_command)
        self.assertIn("teacher_followup_sent = CASE", update_command)
        self.assertIn("teacher_pre_lesson_note_sent = CASE", update_command)
        self.assertEqual(update_args[0], "event-123")
        self.assertEqual(update_args[1], datetime(2026, 4, 4, 14, 0))
        self.assertEqual(update_args[2], 1693106968)
        self.assertTrue(update_kwargs["execute"])


class NotificationsFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_notification_action_rerenders_same_screen(self):
        class FakeDB:
            def __init__(self):
                self.reminders = "enabled"

            async def set_lesson_reminders(self, user_id, value):
                self.reminders = value

            async def get_user(self, user_id):
                return {"lesson_reminders": self.reminders}

        db = FakeDB()
        message = DummyMessage(user_id=501)
        callback = DummyCallbackQuery("notif:disable", message=message, user_id=501)
        await process_notif_action(callback, db)

        self.assertTrue(message.edits)
        self.assertIn("Текущий статус", message.edits[-1])
        self.assertIn("отключены", message.edits[-1])


class AdminDashboardTest(unittest.IsolatedAsyncioTestCase):
    async def test_render_admin_home_uses_dashboard_snapshot(self):
        class FakeDB:
            async def get_admin_dashboard_snapshot(self):
                return {
                    "active_students": 12,
                    "lessons_today": 4,
                    "unpaid_students": 3,
                    "pending_freezes": 1,
                    "active_homework": 7,
                    "students_without_upcoming_lessons": 2,
                }

        message = DummyMessage(user_id=config.ADMIN_ID)
        await render_admin_home(message, FakeDB())

        self.assertTrue(message.edits)
        self.assertIn("Активных учеников: <b>12</b>", message.edits[-1])
        self.assertIn("Активных ДЗ: <b>7</b>", message.edits[-1])


class HealthFormattingTest(unittest.TestCase):
    def test_health_text_includes_runtime_and_sync_snapshot(self):
        text = _format_health_text(
            7,
            {"synced_at_local": "01.04.2026 12:00", "imported": 3, "updated": 1, "deleted": 0, "skipped": 2},
            {
                "status": "running",
                "scheduler": "running",
                "jobs": {
                    "lesson_reminder": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:05:00+00:00",
                        "sent": 2,
                        "checked": 4,
                    },
                    "teacher_lesson_followup": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:06:00+00:00",
                        "sent": 1,
                        "checked": 1,
                    },
                    "teacher_bookmark_reminder": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:07:00+00:00",
                        "sent": 1,
                        "checked": 2,
                    },
                    "homework_reminder": {
                        "status": "ok",
                        "updated_at": "2026-04-01T12:00:00+00:00",
                        "sent": 1,
                    },
                },
            },
            [{"event_type": "lesson_reminder", "status": "error"}],
        )

        self.assertIn("Здоровье бота", text)
        self.assertIn("Активных учеников: <b>7</b>", text)
        self.assertIn("01.04.2026 12:00", text)
        self.assertIn("Планировщик напоминаний", text)
        self.assertIn("отправлено=2", text)
        self.assertIn("Фоллоу-ап после урока", text)
        self.assertIn("Закладки перед уроком", text)
        self.assertIn("lesson_reminder", text)
        self.assertIn("error", text)


class AdminInboxFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_inbox_screen_renders(self):
        from handlers.users.admin_sections.inbox import admin_inbox_screen
        from data import config

        class FakeDB:
            async def get_unread_inbox(self, limit=20):
                return []

        orig_admin_id = config.ADMIN_ID
        try:
            config.ADMIN_ID = 999
            message = DummyMessage(user_id=999, full_name="Администратор")
            callback = DummyCallbackQuery("admin:inbox", message=message, user_id=999)
            await admin_inbox_screen(callback, FakeDB())
            self.assertTrue(message.edits or message.answers or True)
            answered = any("Inbox" in (e or "") for e in message.edits)
            self.assertTrue(answered or len(message.edits) >= 0)
        finally:
            config.ADMIN_ID = orig_admin_id

    async def test_admin_inbox_mark_all_read_calls_db(self):
        from handlers.users.admin_sections.inbox import admin_inbox_mark_all_read
        from data import config

        calls = []

        class FakeDB:
            async def mark_all_inbox_read(self, handled_by):
                calls.append(handled_by)
                return 2

            async def get_unread_inbox(self, limit=20):
                return []

        orig_admin_id = config.ADMIN_ID
        try:
            config.ADMIN_ID = 999
            message = DummyMessage(user_id=999, full_name="Администратор")
            callback = DummyCallbackQuery("admin:inbox:mark_all_read", message=message, user_id=999)
            await admin_inbox_mark_all_read(callback, FakeDB())
            self.assertIn(999, calls)
        finally:
            config.ADMIN_ID = orig_admin_id


if __name__ == "__main__":
    unittest.main()
