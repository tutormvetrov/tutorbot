import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin import (
    admin_lesson_student_selected,
    admin_manage_lessons_student_selected,
)
from handlers.users.admin_sections.calendar_aliases import (
    admin_calendar_alias_student_selected,
)
from handlers.users.admin_sections.common import (
    parse_admin_student_picker_callback_data,
)
from handlers.users.admin_sections.homework import admin_hw_student_selected
from handlers.users.admin_sections.payments import admin_payment_student_selected
from tests.helpers import DummyCallbackQuery, DummyMessage, DummyState
from utils.ui_text import ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT


NINA_ID = 126613312
PICKER_PAGE = 1


class AdminStudentPickerCallbackTest(unittest.TestCase):
    def test_parse_admin_student_picker_callback_data_uses_student_id_segment(self):
        flow, student_id, page = parse_admin_student_picker_callback_data(
            f"admin:student_pick_select:add_homework:{NINA_ID}:{PICKER_PAGE}"
        )

        self.assertEqual(flow, "add_homework")
        self.assertEqual(student_id, NINA_ID)
        self.assertEqual(page, PICKER_PAGE)


class AdminStudentPickerFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_homework_picker_keeps_student_telegram_id(self):
        class FakeDB:
            def __init__(self):
                self.requested_ids = []

            async def get_user(self, telegram_id):
                self.requested_ids.append(telegram_id)
                return {"full_name": "Нина Долгова"}

            async def backfill_homework_materials_for_student(self, student_id):
                self.requested_ids.append(student_id)
                return 0

            async def get_recent_homework_material_mentions(self, student_id):
                self.requested_ids.append(student_id)
                return []

            async def get_top_homework_materials(self, student_id):
                self.requested_ids.append(student_id)
                return []

            async def get_latest_homework_material_mention(self, student_id):
                self.requested_ids.append(student_id)
                return None

            async def get_homework_template_materials(self, student_id, limit=3):
                self.requested_ids.append(student_id)
                return []

            async def has_homework_history(self, student_id):
                self.requested_ids.append(student_id)
                return False

        state = DummyState()
        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery(
            f"admin:student_pick_select:add_homework:{NINA_ID}:{PICKER_PAGE}",
            message=message,
            user_id=config.ADMIN_ID,
        )

        db = FakeDB()
        await admin_hw_student_selected(callback, state, db)

        self.assertEqual(state.data["student_id"], NINA_ID)
        self.assertTrue(all(value == NINA_ID for value in db.requested_ids))
        self.assertEqual(message.edits[-1], ADMIN_ADD_HOMEWORK_BODY_PROMPT_TEXT)

    async def test_homework_picker_shows_template_draft_and_keeps_fsm(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {"full_name": "Нина Долгова", "language": "Французский"}

            async def backfill_homework_materials_for_student(self, student_id):
                return 0

            async def get_recent_homework_material_mentions(self, student_id):
                return [
                    {
                        "material_title": "Livre d’étudiant. Cosmopolite A1",
                        "page_from": 94,
                        "page_to": 95,
                        "exercise_label": "Ex. 5-8",
                    }
                ]

            async def get_top_homework_materials(self, student_id):
                return [{"material_title": "Livre d’étudiant. Cosmopolite A1", "mentions_count": 3}]

            async def get_latest_homework_material_mention(self, student_id):
                return {"material_title": "Livre d’étudiant. Cosmopolite A1", "page_from": 94, "page_to": 95}

            async def get_homework_template_materials(self, student_id, limit=3):
                return [
                    {
                        "material_title": "Livre d’étudiant. Cosmopolite A1",
                        "page_from": 94,
                        "page_to": 95,
                        "exercise_label": "Ex. 5-8",
                    },
                    {
                        "material_title": "Le vocabulaire",
                        "material_kind": "vocabulary",
                        "raw_fragment": "Le vocabulaire. Apprenez des nouvelles expressions ici: https://example.com",
                    }
                ]

            async def has_homework_history(self, student_id):
                return True

        state = DummyState()
        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery(
            f"admin:student_pick_select:add_homework:{NINA_ID}:{PICKER_PAGE}",
            message=message,
            user_id=config.ADMIN_ID,
        )

        await admin_hw_student_selected(callback, state, FakeDB())

        self.assertEqual(state.data["student_id"], NINA_ID)
        self.assertEqual(await state.get_state(), "AdminAddHomework:waiting_for_description")
        self.assertIn("Черновик по статистике", message.edits[-1])
        self.assertIn("<pre>", message.edits[-1])
        self.assertIn("Livre d’étudiant. Cosmopolite A1", message.edits[-1])
        self.assertIn("Ex. 5-8 — pages 94-95;", message.edits[-1])
        self.assertIn("Apprenez des nouvelles expressions ici: https://example.com.", message.edits[-1])
        self.assertNotIn("По прошлым ДЗ", message.edits[-1])
        self.assertNotIn("Чаще всего", message.edits[-1])
        self.assertNotIn("Подсказка", message.edits[-1])
        self.assertNotIn("Продолжить от последнего", message.edits[-1])
        callbacks = [
            button.callback_data
            for row in message.reply_markups[-1].inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("cancel_fsm", callbacks)

    async def test_payment_picker_keeps_student_telegram_id(self):
        state = DummyState()
        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery(
            f"admin:student_pick_select:add_payment:{NINA_ID}:{PICKER_PAGE}",
            message=message,
            user_id=config.ADMIN_ID,
        )

        await admin_payment_student_selected(callback, state)

        self.assertEqual(state.data["student_id"], NINA_ID)

    async def test_lesson_picker_keeps_student_telegram_id(self):
        state = DummyState()
        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery(
            f"admin:student_pick_select:add_lesson:{NINA_ID}:{PICKER_PAGE}",
            message=message,
            user_id=config.ADMIN_ID,
        )

        await admin_lesson_student_selected(callback, state)

        self.assertEqual(state.data["student_id"], NINA_ID)

    async def test_manage_lessons_picker_keeps_student_telegram_id(self):
        class FakeDB:
            def __init__(self):
                self.requested_id = None

            async def get_user(self, telegram_id):
                self.requested_id = telegram_id
                return {"full_name": "Нина Долгова"}

            async def get_non_completed_lessons(self, student_id):
                self.requested_id = student_id
                return []

        state = DummyState()
        await state.set_state("AdminManageLessons:waiting_for_student")
        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery(
            f"admin:student_pick_select:manage_lessons:{NINA_ID}:{PICKER_PAGE}",
            message=message,
            user_id=config.ADMIN_ID,
        )

        db = FakeDB()
        await admin_manage_lessons_student_selected(callback, state, db)

        self.assertEqual(db.requested_id, NINA_ID)
        self.assertIn("Нина Долгова", message.edits[-1])

    async def test_calendar_alias_picker_keeps_student_telegram_id(self):
        class FakeDB:
            def __init__(self):
                self.requested_ids = []

            async def get_user(self, telegram_id):
                self.requested_ids.append(telegram_id)
                return {"full_name": "Нина Долгова"}

            async def get_calendar_student_links_for_student(self, student_id):
                self.requested_ids.append(student_id)
                return []

        state = DummyState()
        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery(
            f"admin:student_pick_select:calendar_aliases:{NINA_ID}:{PICKER_PAGE}",
            message=message,
            user_id=config.ADMIN_ID,
        )

        db = FakeDB()
        await admin_calendar_alias_student_selected(callback, state, db)

        self.assertEqual(state.data["student_id"], NINA_ID)
        self.assertTrue(all(value == NINA_ID for value in db.requested_ids))
        self.assertIn("Нина Долгова", message.edits[-1])
