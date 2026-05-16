import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin_sections.students import (
    admin_pair_invite_link,
    admin_pair_create_partner_entered,
    admin_pair_create_primary_selected,
)
from handlers.users.screens import get_user_home_payload
from handlers.users.start import (
    command_start,
    process_age,
    process_full_name,
    process_language,
    process_level,
    process_pair_partner_name,
    process_role_choice,
)
from tests.helpers import DummyBot, DummyCallbackQuery, DummyConn, DummyMessage, DummyPool, DummyState
from utils.db_api.schema import DatabaseSchemaMixin
from utils.ui_text import build_admin_pair_card_text, build_student_home_text


class StudentPairSchemaTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_creates_pair_tables_and_indexes(self):
        class FakeSchema(DatabaseSchemaMixin):
            def __init__(self):
                self.calls = []

            async def execute(self, query, *args, **kwargs):
                self.calls.append((query, args, kwargs))

        db = FakeSchema()
        await db.create_table_student_groups()

        sql = "\n".join(call[0] for call in db.calls)
        self.assertIn("CREATE TABLE IF NOT EXISTS student_groups", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS student_group_members", sql)
        self.assertIn("primary_student_id BIGINT NOT NULL", sql)
        self.assertIn("balance_mode TEXT NOT NULL DEFAULT 'shared'", sql)
        self.assertIn("homework_mode TEXT NOT NULL DEFAULT 'shared'", sql)
        self.assertIn("naming_mode TEXT NOT NULL DEFAULT 'auto'", sql)
        self.assertIn("common_surname TEXT", sql)
        self.assertIn("invite_token TEXT UNIQUE", sql)
        self.assertIn("invite_used_at TIMESTAMP", sql)
        self.assertIn("student_groups_primary_student_idx", sql)


class StudentPairRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_self_registration_creates_student_profile_and_pair(self):
        bot = DummyBot()
        state = DummyState()
        role_message = DummyMessage(user_id=901, full_name="Иван Петров", bot=bot)
        role_callback = DummyCallbackQuery(
            "role:student_pair",
            message=role_message,
            user_id=901,
            full_name="Иван Петров",
            bot=bot,
        )

        await process_role_choice(role_callback, state)
        await process_full_name(DummyMessage("Иван Петров", user_id=901, bot=bot), state)
        await process_age(DummyMessage("29", user_id=901, bot=bot), state)
        await process_language(DummyMessage("английский", user_id=901, bot=bot), state)

        class FakeDB:
            def __init__(self):
                self.conn = DummyConn()
                self.pool = DummyPool(self.conn)
                self.created_pairs = []
                self.synced = []

            async def create_student_pair(
                self,
                primary_student_id,
                primary_member_name,
                partner_name,
                *,
                onboarding_source="admin",
            ):
                self.created_pairs.append(
                    (primary_student_id, primary_member_name, partner_name, onboarding_source)
                )
                return 42

            async def sync_parent_links_for_student(self, student_id, full_name):
                self.synced.append((student_id, full_name))
                return 0

        db = FakeDB()
        level_message = DummyMessage(user_id=901, full_name="Иван Петров", bot=bot)
        level_callback = DummyCallbackQuery(
            "level:B1",
            message=level_message,
            user_id=901,
            full_name="Иван Петров",
            bot=bot,
        )
        await process_level(level_callback, state, db)
        self.assertEqual(state.state.state, "Registration:waiting_for_pair_partner_name")
        self.assertIn("второго участника", level_message.edits[-1])

        partner_message = DummyMessage("Мария Петрова", user_id=901, full_name="Иван Петров", bot=bot)
        await process_pair_partner_name(partner_message, state, db)

        self.assertIsNone(state.state)
        self.assertIn("INSERT INTO users", db.conn.executed[0][0])
        self.assertEqual(
            db.created_pairs,
            [(901, "Иван Петров", "Мария Петрова", "self_registration")],
        )
        self.assertEqual(db.synced, [(901, "Иван Петров")])
        self.assertNotIn("901", bot.sent_messages[-1].text)
        self.assertIn("Основной контакт: Иван Петров", bot.sent_messages[-1].text)
        admin_callbacks = [
            button.callback_data
            for row in bot.sent_messages[-1].reply_markup.inline_keyboard
            for button in row
        ]
        self.assertEqual(admin_callbacks, ["admin:pair_invite:42", "admin:pair:42"])
        self.assertIn("Регистрация пары завершена", partner_message.answers[-1])
        self.assertIn("общий баланс", partner_message.answers[-1].lower())


class StudentPairAdminFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_admin_can_create_pair_for_existing_student(self):
        bot = DummyBot()
        state = DummyState()

        class FakeDB:
            def __init__(self):
                self.created_pairs = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Иван Петров",
                    "role": "student",
                    "is_active": True,
                }

            async def create_student_pair(
                self,
                primary_student_id,
                primary_member_name,
                partner_name,
                *,
                onboarding_source="admin",
            ):
                self.created_pairs.append(
                    (primary_student_id, primary_member_name, partner_name, onboarding_source)
                )
                return 7

            async def get_student_pair(self, group_id):
                return {
                    "id": group_id,
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                    "member_names": ["Иван Петров", "Мария Петрова"],
                    "lesson_balance": 4,
                    "active_homework_count": 1,
                    "next_lesson_date": None,
                }

        db = FakeDB()
        callback = DummyCallbackQuery(
            "admin:pairs:add_primary:555",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )
        await admin_pair_create_primary_selected(callback, state, db)

        self.assertEqual(state.state.state, "AdminCreatePair:waiting_for_partner_name")
        self.assertIn("Иван Петров", callback.message.edits[-1])

        message = DummyMessage("Мария Петрова", user_id=config.ADMIN_ID, bot=bot)
        await admin_pair_create_partner_entered(message, state, db)

        self.assertIsNone(state.state)
        self.assertEqual(db.created_pairs, [(555, "Иван Петров", "Мария Петрова", "admin")])
        self.assertIn("Учебная пара создана", message.answers[-1])
        callbacks = [button.callback_data for row in message.reply_markups[-1].inline_keyboard for button in row]
        self.assertIn("admin:pair_invite:7", callbacks)
        self.assertIn("admin:pair_name:primary:7", callbacks)
        self.assertIn("admin:pair_name:partner:7", callbacks)
        self.assertIn("admin:student_card:555:0", callbacks)

    async def test_admin_can_generate_partner_invite_link(self):
        bot = DummyBot()

        class FakeDB:
            async def ensure_student_pair_invite(self, group_id):
                return {
                    "group_id": group_id,
                    "member_name": "Мария Петрова",
                    "invite_token": "abc_DEF-123",
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                }

            async def get_student_pair(self, group_id):
                return {
                    "id": group_id,
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                    "member_names": ["Иван Петров", "Мария Петрова"],
                    "lesson_balance": 4,
                    "active_homework_count": 1,
                    "next_lesson_date": None,
                }

        callback = DummyCallbackQuery(
            "admin:pair_invite:7",
            message=DummyMessage(user_id=config.ADMIN_ID, bot=bot),
            user_id=config.ADMIN_ID,
            bot=bot,
        )
        await admin_pair_invite_link(callback, FakeDB())

        self.assertIn("Ссылка для второго участника", callback.message.edits[-1])
        self.assertIn("https://t.me/tutorbot_test?start=pair_abc_DEF-123", callback.message.edits[-1])
        self.assertEqual(callback.answers[-1].text, "Ссылка готова.")


class StudentPairInviteStartTest(unittest.IsolatedAsyncioTestCase):
    async def test_partner_can_join_pair_from_start_link(self):
        bot = DummyBot()
        state = DummyState()

        class FakeDB:
            def __init__(self):
                self.accepted = []

            async def get_student_pair_invite(self, token):
                return {
                    "member_id": 2,
                    "group_id": 7,
                    "student_id": None,
                    "member_name": "Мария Петрова",
                    "invite_token": token,
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                }

            async def get_user(self, telegram_id):
                if telegram_id == 902:
                    return {
                        "telegram_id": 902,
                        "full_name": "Мария Петрова",
                        "username": "maria",
                        "role": "student",
                        "is_active": True,
                    }
                return None

            async def accept_student_pair_invite(self, token, telegram_id, telegram_full_name, username=None):
                self.accepted.append((token, telegram_id, telegram_full_name, username))
                return {
                    "id": 7,
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                    "member_names": ["Иван Петров", "Мария Петрова"],
                    "lesson_balance": 2,
                    "active_homework_count": 1,
                    "next_lesson_date": None,
                }

            async def get_student_pair_for_student(self, student_id):
                return {
                    "id": 7,
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                    "member_names": ["Иван Петров", "Мария Петрова"],
                    "lesson_balance": 2,
                    "active_homework_count": 1,
                    "next_lesson_date": None,
                }

            async def get_active_lessons(self, student_id):
                self.last_lessons_student_id = student_id
                return []

            async def get_student_homework(self, student_id, status):
                self.last_homework_student_id = student_id
                return [{"id": 1, "title": "Read", "status": status}]

            async def get_student_lesson_balance(self, student_id):
                self.last_balance_student_id = student_id
                return 2

        db = FakeDB()
        message = DummyMessage(
            "/start pair_abc_DEF-123",
            user_id=902,
            full_name="Telegram Maria",
            username="maria",
            bot=bot,
        )

        await command_start(message, state, db)

        self.assertEqual(db.accepted, [("abc_DEF-123", 902, "Telegram Maria", "maria")])
        self.assertIn("Вы подключены к учебной паре", message.answers[-1])
        self.assertEqual(db.last_lessons_student_id, 555)
        self.assertEqual(db.last_homework_student_id, 555)
        self.assertEqual(db.last_balance_student_id, 555)
        self.assertIn("Второй участник подключился", bot.sent_messages[-1].text)
        self.assertNotIn("902", bot.sent_messages[-1].text)
        self.assertIn("@maria", bot.sent_messages[-1].text)


class StudentPairSharedCabinetTest(unittest.IsolatedAsyncioTestCase):
    async def test_partner_home_payload_uses_primary_learning_data(self):
        class FakeDB:
            def __init__(self):
                self.calls = []

            async def get_user(self, telegram_id):
                return {
                    "telegram_id": telegram_id,
                    "full_name": "Мария Петрова",
                    "role": "student",
                    "is_active": True,
                }

            async def get_student_pair_for_student(self, student_id):
                return {
                    "id": 7,
                    "title": "Иван Петров + Мария Петрова",
                    "primary_student_id": 555,
                    "primary_student_name": "Иван Петров",
                    "member_names": ["Иван Петров", "Мария Петрова"],
                    "lesson_balance": 4,
                    "active_homework_count": 1,
                    "next_lesson_date": None,
                }

            async def get_active_lessons(self, student_id):
                self.calls.append(("lessons", student_id))
                return []

            async def get_student_homework(self, student_id, status):
                self.calls.append(("homework", student_id, status))
                return []

            async def get_student_lesson_balance(self, student_id):
                self.calls.append(("balance", student_id))
                return 4

        db = FakeDB()
        text, _ = await get_user_home_payload(db, 902)

        self.assertIn("Пара", text)
        self.assertIn(("lessons", 555), db.calls)
        self.assertIn(("homework", 555, "active"), db.calls)
        self.assertIn(("balance", 555), db.calls)


class StudentPairUiTextTest(unittest.TestCase):
    def test_student_home_and_admin_pair_card_show_shared_mode(self):
        pair = {
            "id": 7,
            "title": "Иван Петров + Мария Петрова",
            "primary_student_id": 555,
            "primary_student_name": "Иван Петров",
            "member_names": ["Иван Петров", "Мария Петрова"],
            "lesson_balance": 3,
            "active_homework_count": 2,
            "next_lesson_date": None,
        }

        home_text = build_student_home_text(
            {"full_name": "Иван Петров"},
            balance=3,
            active_homework_count=2,
            pair=pair,
        )
        card_text = build_admin_pair_card_text(pair)

        self.assertIn("Пара", home_text)
        self.assertIn("одно домашнее задание на двоих", home_text)
        self.assertIn("Баланс: <b>общий</b>", card_text)
        self.assertIn("Темп: <b>один на двоих</b>", card_text)


if __name__ == "__main__":
    unittest.main()
