import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pymupdf

from data import config
from handlers.users.admin_sections.payments import _parse_rate_line, admin_pricing_rate_entered
from handlers.users.admin_sections.study_plans import admin_study_plan_publish
from handlers.users.callbacks import process_requisites, process_study_plan, process_study_plan_file, process_study_plan_toggle
from states.registration import AdminPricing
from tests.helpers import DummyBot, DummyCallbackQuery, DummyMessage, DummyState
from utils.db_api.schema import DatabaseSchemaMixin
from utils.db_api.study_plans import DatabaseStudyPlanMixin
from utils.pdf_learning_plan import parse_learning_plan_pdf
from utils.ui_text import build_admin_study_plan_preview_text


class LearningPlanParserTest(unittest.TestCase):
    def test_text_pdf_parses_summary(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text(
                (72, 72),
                "Week 1. Grammar revision and speaking practice.\n"
                "Week 2. Reading and vocabulary expansion.\n"
                "Week 3. Listening practice and exam-style questions.\n"
                "Week 4. Review and checkpoint lesson.",
            )
            doc.save(tmp.name)
            doc.close()

            parsed = parse_learning_plan_pdf(tmp.name)

        self.assertEqual(parsed.status, "ok")
        self.assertEqual(parsed.pages_count, 1)
        self.assertIn("Grammar revision", parsed.text)
        self.assertIn("• Week 1", parsed.summary)

    def test_table_api_rows_are_added_to_preview_text(self):
        class FakeTable:
            def extract(self):
                return [["Week", "Focus"], ["1", "Speaking"], ["2", "Grammar"]]

        class FakePage:
            def get_text(self, *args, **kwargs):
                return "Three month plan"

            def find_tables(self):
                return type("Finder", (), {"tables": [FakeTable()]})()

        class FakeDoc:
            def __len__(self):
                return 1

            def __iter__(self):
                return iter([FakePage()])

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("utils.pdf_learning_plan.pymupdf.open", return_value=FakeDoc()):
            parsed = parse_learning_plan_pdf("fake.pdf")

        self.assertEqual(parsed.tables_count, 1)
        self.assertIn("Week | Focus", parsed.text)
        self.assertIn("1 | Speaking", parsed.text)

    def test_blank_pdf_requires_manual_summary(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            doc = pymupdf.open()
            doc.new_page()
            doc.save(tmp.name)
            doc.close()

            parsed = parse_learning_plan_pdf(tmp.name)

        self.assertEqual(parsed.status, "needs_manual_summary")
        self.assertEqual(parsed.summary, "")
        self.assertTrue(parsed.warnings)

    def test_admin_preview_includes_file_name(self):
        text = build_admin_study_plan_preview_text(
            {
                "file_name": "three-month-plan.pdf",
                "pages_count": 2,
                "tables_count": 1,
                "status": "ok",
                "text": "Week 1. Speaking practice.",
                "warnings": [],
            },
            "Фокус на разговорной практике.",
        )

        self.assertIn("three-month-plan.pdf", text)


class StudyPlanSchemaTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_creates_learning_plan_and_pricing_tables(self):
        class FakeSchema(DatabaseSchemaMixin):
            def __init__(self):
                self.calls = []

            async def execute(self, query, *args, **kwargs):
                self.calls.append((query, args, kwargs))

        db = FakeSchema()
        await db.create_table_learning_plans()
        await db.create_table_lesson_pricing_rates()

        sql = "\n".join(call[0] for call in db.calls)
        self.assertIn("CREATE TABLE IF NOT EXISTS student_learning_plans", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS study_plan_checklist_items", sql)
        self.assertIn("student_learning_plans_one_active_idx", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS lesson_pricing_rates", sql)
        self.assertIn("UNIQUE (group_size, duration_minutes)", sql)


class StudyPlanMixinTest(unittest.IsolatedAsyncioTestCase):
    async def test_pricing_context_uses_pair_size_and_primary_duration(self):
        class FakeDB(DatabaseStudyPlanMixin):
            async def get_user(self, telegram_id):
                if telegram_id == 555:
                    return {"telegram_id": 555, "lesson_duration_minutes": 75}
                return {"telegram_id": telegram_id, "lesson_duration_minutes": 90}

            async def get_student_pair_for_student(self, student_id):
                return {
                    "id": 7,
                    "primary_student_id": 555,
                    "member_names": ["Анна", "Полина", "Дима"],
                }

            async def get_pricing_rate(self, group_size, duration_minutes):
                self.lookup = (group_size, duration_minutes)
                return {"group_size": group_size, "duration_minutes": duration_minutes, "amount": 7200, "currency": "RUB"}

        db = FakeDB()
        context = await db.get_student_pricing_context(777)

        self.assertEqual(db.lookup, (3, 75))
        self.assertEqual(context["group_size"], 3)
        self.assertEqual(context["duration_minutes"], 75)
        self.assertEqual(context["rate"]["amount"], 7200)

    async def test_parent_digest_maps_pair_partner_to_primary_plan(self):
        class FakeDB(DatabaseStudyPlanMixin):
            async def execute(self, query, *args, **kwargs):
                self.query = query
                return []

        db = FakeDB()
        await db.get_learning_plan_parent_digest_rows()

        self.assertIn("COALESCE(g.primary_student_id, sp.student_id) AS plan_student_id", db.query)
        self.assertIn("JOIN student_learning_plans p ON p.student_id = cp.plan_student_id", db.query)
        self.assertIn("LEFT JOIN next_lessons n ON n.student_id = cp.plan_student_id", db.query)


class StudyPlanStudentFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_student_opens_plan_toggles_checklist_and_gets_pdf(self):
        class FakeDB:
            def __init__(self):
                self.toggled = []

            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "full_name": "Анна Иванова", "role": "student", "is_active": True}

            async def get_student_pair_for_student(self, student_id):
                return None

            async def get_active_learning_plan(self, student_id):
                return {"id": 9, "student_id": student_id, "status": "active", "summary": "Фокус: устная практика"}

            async def ensure_study_plan_checklist(self, student_id):
                return {
                    "lesson": {"id": 4, "lesson_date": datetime(2026, 4, 8, 16, 0)},
                    "items": [{"id": 1, "title": "Открыть активное ДЗ", "status": "pending"}],
                }

            async def get_student_homework(self, student_id, status):
                return [{"id": 77, "title": "Homework"}]

            async def get_learning_plan_by_id(self, plan_id):
                return {"id": plan_id, "student_id": 555, "status": "active", "file_id": "tg-file-id"}

            async def toggle_study_plan_checklist_item(self, item_id, student_id):
                self.toggled.append((item_id, student_id))
                return {"id": item_id, "status": "done"}

        bot = DummyBot()
        db = FakeDB()
        message = DummyMessage(user_id=555, bot=bot)
        callback = DummyCallbackQuery("study_plan", message=message, user_id=555, bot=bot)

        await process_study_plan(callback, db)

        self.assertIn("Учебный план", message.edits[-1])
        self.assertIn("Фокус: устная практика", message.edits[-1])
        callbacks = [button.callback_data for row in message.reply_markups[-1].inline_keyboard for button in row if button.callback_data]
        self.assertIn("study_plan:file:9", callbacks)
        self.assertIn("study_plan:toggle:1", callbacks)

        toggle_callback = DummyCallbackQuery("study_plan:toggle:1", message=message, user_id=555, bot=bot)
        await process_study_plan_toggle(toggle_callback, db)
        self.assertEqual(db.toggled, [(1, 555)])

        file_callback = DummyCallbackQuery("study_plan:file:9", message=message, user_id=555, bot=bot)
        await process_study_plan_file(file_callback, db)
        self.assertEqual(bot.sent_documents[-1].document, "tg-file-id")

    async def test_student_requisites_uses_pricing_context(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "full_name": "Анна Иванова", "role": "student", "is_active": True}

            async def get_student_pair_for_student(self, student_id):
                return None

            async def get_student_pricing_context(self, student_id):
                return {
                    "group_size": 2,
                    "duration_minutes": 90,
                    "rate": {"group_size": 2, "duration_minutes": 90, "amount": 5000, "currency": "RUB"},
                }

        message = DummyMessage(user_id=555)
        callback = DummyCallbackQuery("payment:requisites", message=message, user_id=555)

        await process_requisites(callback, FakeDB())

        self.assertIn("5000 ₽ / 90 минут", message.edits[-1])


class StudyPlanAdminFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_publish_archives_old_plan_and_notifies_recipients(self):
        state = DummyState()
        await state.update_data(
            student_id=555,
            parsed_pdf={
                "text": "Full parsed text",
                "status": "ok",
                "warnings": [],
                "pages_count": 1,
                "tables_count": 0,
            },
            plan_summary="Фокус на разговорной практике и повторении грамматики.",
            plan_summary_manual=False,
            pdf_file_id="tg-plan-file",
            pdf_file_unique_id="unique-plan",
            pdf_file_name="plan.pdf",
            pdf_mime_type="application/pdf",
        )

        class FakeDB:
            def __init__(self):
                self.published = []

            async def publish_learning_plan(self, student_id, **kwargs):
                self.published.append((student_id, kwargs))
                return 12

            async def get_study_plan_recipients(self, student_id):
                return [555, 556]

        bot = DummyBot()
        callback = DummyCallbackQuery(
            "admin:study_plan_publish",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )
        db = FakeDB()

        await admin_study_plan_publish(callback, state, db)

        self.assertEqual(state.state, None)
        self.assertEqual(db.published[0][0], 555)
        self.assertEqual(db.published[0][1]["file_id"], "tg-plan-file")
        self.assertEqual([m.chat_id for m in bot.sent_messages], [555, 556])

    async def test_admin_cannot_publish_weak_parse_without_manual_summary(self):
        state = DummyState()
        await state.update_data(
            student_id=555,
            parsed_pdf={"text": "Short text", "status": "needs_manual_summary", "warnings": ["low text"]},
            plan_summary="Автоматическая выжимка достаточно длинная, но парсинг слабый.",
            plan_summary_manual=False,
            pdf_file_id="tg-plan-file",
        )

        class FakeDB:
            def __init__(self):
                self.published = []

            async def publish_learning_plan(self, student_id, **kwargs):
                self.published.append((student_id, kwargs))
                return 12

        callback = DummyCallbackQuery(
            "admin:study_plan_publish",
            message=DummyMessage(user_id=config.ADMIN_ID),
            user_id=config.ADMIN_ID,
        )
        db = FakeDB()

        await admin_study_plan_publish(callback, state, db)

        self.assertEqual(db.published, [])
        self.assertEqual(callback.answers[-1].text, "Сначала вручную проверьте и сохраните выжимку.")
        self.assertTrue(callback.answers[-1].show_alert)


class PricingAdminFlowTest(unittest.IsolatedAsyncioTestCase):
    def test_parse_rate_line_supports_arbitrary_group_size(self):
        self.assertEqual(_parse_rate_line("3 75 6000 RUB"), (3, 75, 6000.0, "RUB"))
        self.assertEqual(_parse_rate_line("2 90 5000 eur"), (2, 90, 5000.0, "EUR"))
        self.assertIsNone(_parse_rate_line("0 90 5000 RUB"))

    async def test_admin_saves_pricing_rate(self):
        state = DummyState()
        await state.set_state(AdminPricing.waiting_for_rate)

        class FakeDB:
            def __init__(self):
                self.calls = []

            async def upsert_pricing_rate(self, group_size, duration, amount, currency):
                self.calls.append((group_size, duration, amount, currency))

        message = DummyMessage("4 60 8000 RUB", user_id=config.ADMIN_ID)
        db = FakeDB()

        await admin_pricing_rate_entered(message, state, db)

        self.assertEqual(state.state, None)
        self.assertEqual(db.calls, [(4, 60, 8000.0, "RUB")])
        self.assertIn("Тариф сохранён", message.answers[-1])


class ChecklistLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_checklist_is_created_for_next_lesson_only(self):
        now = datetime.now()

        class FakeConn:
            def __init__(self):
                self.inserted = []

            def transaction(self):
                return self

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def execute(self, query, *args):
                self.inserted.append(args)

        class FakePool:
            def __init__(self, conn):
                self.conn = conn

            def acquire(self):
                return self.conn

        class FakeDB(DatabaseStudyPlanMixin):
            def __init__(self):
                self.conn = FakeConn()
                self.pool = FakePool(self.conn)
                self.fetch_count = 0

            async def get_next_study_plan_lesson(self, student_id):
                return {"id": 42, "lesson_date": now + timedelta(days=1)}

            async def _build_auto_study_plan_items(self, student_id):
                return ["Открыть активное ДЗ", "Подготовить вопрос"]

            async def execute(self, query, *args, **kwargs):
                if kwargs.get("fetch"):
                    self.fetch_count += 1
                    if self.fetch_count == 1:
                        return []
                    return [
                        {"id": 1, "student_id": 555, "lesson_id": 42, "title": "Открыть активное ДЗ", "status": "pending"},
                        {"id": 2, "student_id": 555, "lesson_id": 42, "title": "Подготовить вопрос", "status": "pending"},
                    ]
                return None

        db = FakeDB()
        result = await db.ensure_study_plan_checklist(555)

        self.assertEqual(len(db.conn.inserted), 2)
        self.assertEqual(result["lesson"]["id"], 42)
        self.assertEqual([item["title"] for item in result["items"]], ["Открыть активное ДЗ", "Подготовить вопрос"])
