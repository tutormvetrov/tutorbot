import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from handlers.users.callbacks import (
    process_parent_child_home,
    process_parent_child_homework,
    process_parent_child_homework_detail,
    process_parent_child_homework_file,
    process_parent_child_payments,
    process_parent_child_schedule,
    process_parent_child_study_plan,
    process_parent_engagement_toggle,
)
from handlers.users.screens import get_user_home_payload
from handlers.users.start import (
    command_start,
    process_age,
    process_child_age,
    process_child_name,
    process_engagement_mode_choice,
    process_full_name,
)
from tests.helpers import DummyBot, DummyCallbackQuery, DummyConn, DummyMessage, DummyPool, DummyState
from utils.ui_text import child_traffic_light, lesson_balance_label


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


def _make_parent_registration_db():
    class FakeDB:
        def __init__(self):
            self.conn = DummyConn()
            self.pool = DummyPool(self.conn)
            self.link_calls = []
            self.children_overview = []

        async def find_active_student_by_name(self, full_name):
            self.link_calls.append(("find", full_name))
            return {"telegram_id": 555123, "full_name": full_name, "role": "student", "is_active": True}

        async def upsert_parent_student_link(self, parent_id, student_info, student_id=None):
            self.link_calls.append(("link", parent_id, student_info, student_id))
            return 1

        async def get_parent_children_overview(self, parent_id):
            return self.children_overview

    return FakeDB()


class ParentRegistrationFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_parent_registration_active_mode_creates_profile_and_child_link(self):
        state = DummyState()
        await state.update_data(role="parent", reg_total=6)

        await process_full_name(DummyMessage("Мария Иванова", user_id=801), state)
        await process_age(DummyMessage("35", user_id=801), state)
        await process_child_name(DummyMessage("Анна Иванова", user_id=801), state)

        age_message = DummyMessage("12", user_id=801, full_name="Мария Иванова")
        await process_child_age(age_message, state)
        self.assertEqual(state.state.state, "Registration:waiting_for_engagement_mode")
        self.assertTrue(any("Хочу быть в курсе" in t for t in _keyboard_texts(age_message.reply_markups[-1])))

        db = _make_parent_registration_db()
        finish_message = DummyMessage(user_id=801, full_name="Мария Иванова")
        callback = DummyCallbackQuery(
            "engagement:active",
            message=finish_message,
            user_id=801,
            full_name="Мария Иванова",
        )
        await process_engagement_mode_choice(callback, state, db)

        self.assertIsNone(state.state)
        self.assertTrue(db.conn.executed)
        insert_sql = db.conn.executed[0][0]
        self.assertIn("INSERT INTO users", insert_sql)
        self.assertIn("'parent'", insert_sql)
        self.assertIn("engagement_mode", insert_sql)
        self.assertEqual(db.conn.executed[0][1][-1], "active")
        self.assertEqual(
            db.link_calls,
            [
                ("find", "Анна Иванова"),
                ("link", 801, "Анна Иванова (12)", 555123),
            ],
        )
        self.assertIn("Связь с учеником найдена", finish_message.answers[-1])
        self.assertIn("активное наблюдение", finish_message.answers[-1])
        keyboard_texts = _keyboard_texts(finish_message.reply_markups[-1])
        self.assertIn("👨‍👩‍👧 Мои дети", keyboard_texts)

    async def test_parent_registration_trust_mode_persists_choice(self):
        state = DummyState()
        await state.update_data(role="parent", reg_total=6)
        await process_full_name(DummyMessage("Мария Иванова", user_id=802), state)
        await process_age(DummyMessage("35", user_id=802), state)
        await process_child_name(DummyMessage("Иван Иванов", user_id=802), state)
        await process_child_age(DummyMessage("10", user_id=802), state)

        db = _make_parent_registration_db()
        message = DummyMessage(user_id=802)
        callback = DummyCallbackQuery(
            "engagement:trust",
            message=message,
            user_id=802,
        )
        await process_engagement_mode_choice(callback, state, db)

        self.assertEqual(db.conn.executed[0][1][-1], "trust")
        self.assertIn("доверие преподавателю", message.answers[-1])


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
        self.assertIn("parent:child:7", [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data])
        child_button_texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertTrue(any("Анна Иванова" in t for t in child_button_texts))
        self.assertTrue(any(t.startswith(("🟢", "🟡", "🔴", "⏳")) for t in child_button_texts))

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

            async def get_student_transactions(self, student_id, limit=15):
                return [
                    {
                        "type": "payment_added",
                        "amount_lessons": 4,
                        "created_at": datetime(2026, 4, 1),
                        "payment_amount": 3000,
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


class ParentEngagementModeTest(unittest.IsolatedAsyncioTestCase):
    def _trust_db(self):
        class FakeDB:
            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Иванова",
                    "role": "parent",
                    "is_active": True,
                    "engagement_mode": "trust",
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

        return FakeDB()

    async def test_trust_mode_child_keyboard_hides_homework_and_study_plan(self):
        db = self._trust_db()
        message = DummyMessage(user_id=910, full_name="Мария Иванова")
        callback = DummyCallbackQuery(
            "parent:child:7",
            message=message,
            user_id=910,
            full_name="Мария Иванова",
        )
        await process_parent_child_home(callback, db)

        callback_datas = [
            button.callback_data
            for row in message.reply_markups[-1].inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("parent:child:7:schedule", callback_datas)
        self.assertIn("parent:child:7:payments", callback_datas)
        self.assertNotIn("parent:child:7:homework:active", callback_datas)
        self.assertNotIn("parent:child:7:study_plan", callback_datas)

    async def test_trust_mode_homework_callback_blocked(self):
        db = self._trust_db()
        message = DummyMessage(user_id=910)
        callback = DummyCallbackQuery(
            "parent:child:7:homework:active",
            message=message,
            user_id=910,
        )
        await process_parent_child_homework(callback, db)
        self.assertEqual(message.edits, [])
        self.assertTrue(callback.answers)
        self.assertIn("доверительный", callback.answers[-1].text)

    async def test_trust_mode_study_plan_callback_blocked(self):
        db = self._trust_db()
        message = DummyMessage(user_id=910)
        callback = DummyCallbackQuery(
            "parent:child:7:study_plan",
            message=message,
            user_id=910,
        )
        await process_parent_child_study_plan(callback, db)
        self.assertEqual(message.edits, [])
        self.assertIn("доверительный", callback.answers[-1].text)

    async def test_engagement_toggle_flips_mode_and_rerenders_profile(self):
        class FakeDB:
            def __init__(self):
                self.mode = "active"
                self.set_calls = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Иванова",
                    "role": "parent",
                    "is_active": True,
                    "engagement_mode": self.mode,
                }

            async def get_parent_children_overview(self, parent_id):
                return []

            async def set_parent_engagement_mode(self, parent_id, mode):
                self.set_calls.append((parent_id, mode))
                self.mode = mode
                return mode

        db = FakeDB()
        message = DummyMessage(user_id=920, full_name="Мария Иванова")
        callback = DummyCallbackQuery(
            "parent:engagement:toggle",
            message=message,
            user_id=920,
            full_name="Мария Иванова",
        )
        await process_parent_engagement_toggle(callback, db)

        self.assertEqual(db.set_calls, [(920, "trust")])
        keyboard_texts = _keyboard_texts(message.reply_markups[-1])
        self.assertTrue(any("Режим: доверие" in t for t in keyboard_texts))


class ParentSelfDeleteTest(unittest.IsolatedAsyncioTestCase):
    async def test_parent_self_delete_uses_preserving_history(self):
        from handlers.users.callbacks import process_self_delete_confirm

        class FakeDB:
            def __init__(self):
                self.full_calls = []
                self.preserving_calls = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Иванова",
                    "role": "parent",
                    "is_active": True,
                }

            async def get_admin_preview_session(self, admin_id):
                return None

            async def delete_user_fully(self, telegram_id):
                self.full_calls.append(telegram_id)

            async def delete_parent_preserving_history(self, telegram_id):
                self.preserving_calls.append(telegram_id)

        db = FakeDB()
        message = DummyMessage(user_id=931)
        callback = DummyCallbackQuery(
            "self_delete:confirm",
            message=message,
            user_id=931,
        )
        await process_self_delete_confirm(callback, db)
        self.assertEqual(db.preserving_calls, [931])
        self.assertEqual(db.full_calls, [])

    async def test_parent_self_delete_warning_uses_parent_snapshot(self):
        from handlers.users.callbacks import process_profile_delete_me

        class FakeDB:
            def __init__(self):
                self.snapshot_called_with = None
                self.user_snapshot_called = False

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Иванова",
                    "role": "parent",
                    "is_active": True,
                }

            async def get_admin_preview_session(self, admin_id):
                return None

            async def get_parent_deletion_snapshot(self, telegram_id):
                self.snapshot_called_with = telegram_id
                return {"children_count": 2, "linked_children_count": 1, "payments_as_payer": 5}

            async def get_user_deletion_snapshot(self, telegram_id):
                self.user_snapshot_called = True
                return {}

        db = FakeDB()
        message = DummyMessage(user_id=932)
        callback = DummyCallbackQuery(
            "profile:delete_me",
            message=message,
            user_id=932,
        )
        await process_profile_delete_me(callback, db)
        self.assertEqual(db.snapshot_called_with, 932)
        self.assertFalse(db.user_snapshot_called)
        self.assertIn("Связей с учениками", message.edits[-1])
        self.assertIn("<b>2</b>", message.edits[-1])


class ParentBlockedStudentCallbacksTest(unittest.IsolatedAsyncioTestCase):
    async def test_parent_blocked_from_schedule_callback(self):
        from handlers.users.callbacks import process_menu_choice

        class FakeDB:
            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "role": "parent", "is_active": True}

            async def get_admin_preview_session(self, admin_id):
                return None

        db = FakeDB()
        message = DummyMessage(user_id=940)
        callback = DummyCallbackQuery("schedule", message=message, user_id=940)
        await process_menu_choice(callback, db)
        self.assertEqual(message.edits, [])
        self.assertIn("ученикам", callback.answers[-1].text)

    async def test_parent_blocked_from_homework_root_callback(self):
        from handlers.users.callbacks import process_homework

        class FakeDB:
            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "role": "parent", "is_active": True}

            async def get_admin_preview_session(self, admin_id):
                return None

        db = FakeDB()
        message = DummyMessage(user_id=941)
        callback = DummyCallbackQuery("homework", message=message, user_id=941)
        await process_homework(callback, db)
        self.assertEqual(message.edits, [])
        self.assertIn("ученикам", callback.answers[-1].text)


class ParentMaterialsTest(unittest.IsolatedAsyncioTestCase):
    async def test_parent_materials_loads_global_resources_not_personal(self):
        from handlers.users.callbacks import process_materials

        class FakeDB:
            def __init__(self):
                self.student_resource_calls = []
                self.global_called = False

            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "role": "parent", "is_active": True}

            async def get_admin_preview_session(self, admin_id):
                return None

            async def list_student_resources(self, owner_id):
                self.student_resource_calls.append(owner_id)
                return []

            async def list_global_resources(self):
                self.global_called = True
                return [{"id": 1, "label": "Общие материалы", "url": "https://example.com", "provider": None, "is_primary": False, "sort_order": 0, "student_id": None}]

        db = FakeDB()
        message = DummyMessage(user_id=950)
        callback = DummyCallbackQuery("materials", message=message, user_id=950)
        await process_materials(callback, db)
        self.assertTrue(db.global_called)
        self.assertEqual(db.student_resource_calls, [])


class ParentReplyPaymentChildContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_reply_payment_with_child_link_id_includes_child_name_in_context(self):
        from handlers.users.callbacks import start_student_reply

        class FakeDB:
            async def get_user(self, telegram_id):
                return {"telegram_id": telegram_id, "role": "parent", "is_active": True}

            async def get_admin_preview_session(self, admin_id):
                return None

            async def get_parent_child_link(self, parent_id, link_id):
                return {
                    "link_id": link_id,
                    "child_label": "Анна Иванова",
                    "student_id": 707,
                    "link_status": "linked",
                }

        db = FakeDB()
        state = DummyState()
        message = DummyMessage(user_id=960)
        callback = DummyCallbackQuery(
            "reply:payment:child:7",
            message=message,
            user_id=960,
        )

        from data import config as data_config

        original_admin_id = getattr(data_config, "ADMIN_ID", None)
        data_config.ADMIN_ID = 1
        try:
            await start_student_reply(callback, state, db)
        finally:
            data_config.ADMIN_ID = original_admin_id

        data = await state.get_data()
        self.assertIn("по оплате за", data.get("reply_context_label", ""))
        self.assertIn("Анна Иванова", data.get("reply_context_label", ""))
        self.assertEqual(data.get("reply_child_link_id"), 7)


class ParentTrafficLightTest(unittest.TestCase):
    def _child(self, link_status="linked", next_lesson_date=datetime.now(), lesson_balance=3, overdue_homework_count=0):
        return {
            "link_status": link_status,
            "next_lesson_date": next_lesson_date,
            "lesson_balance": lesson_balance,
            "overdue_homework_count": overdue_homework_count,
        }

    def test_linked_child_with_lesson_and_balance_is_green(self):
        self.assertEqual(child_traffic_light(self._child()), "🟢")

    def test_pending_link_is_hourglass(self):
        self.assertEqual(child_traffic_light(self._child(link_status="waiting_link")), "⏳")

    def test_zero_balance_is_red(self):
        self.assertEqual(child_traffic_light(self._child(lesson_balance=0)), "🔴")

    def test_overdue_homework_is_yellow(self):
        self.assertEqual(child_traffic_light(self._child(overdue_homework_count=2)), "🟡")

    def test_no_lesson_is_red(self):
        self.assertEqual(child_traffic_light(self._child(next_lesson_date=None)), "🔴")
