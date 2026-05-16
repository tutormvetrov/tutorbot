import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app import DatabaseMiddleware
from data import config
from handlers.users.admin import (
    admin_blocked,
    admin_blocked_add_start,
    admin_blocked_add_text,
    admin_blocked_unblock,
    command_block,
    command_blocked,
    command_unblock,
)
from keyboards.inline import admin_service_keyboard
from states.registration import AdminBlockTelegramId
from tests.helpers import DummyCallbackQuery, DummyMessage, DummyState
from utils.ui_text import BLOCKED_ACCOUNT_ALERT, BLOCKED_ACCOUNT_TEXT


class _AccessDB:
    def __init__(self, blocked_ids=None, users=None):
        self.blocked_ids = set(blocked_ids or [])
        self.users = dict(users or {})

    async def is_telegram_id_blocked(self, telegram_id):
        return telegram_id in self.blocked_ids

    async def get_user(self, telegram_id):
        return self.users.get(telegram_id)


class _AdminBlockDB:
    def __init__(self):
        self.users = {
            777: {
                "telegram_id": 777,
                "full_name": "Ann Student",
                "role": "student",
                "is_active": True,
            },
            888: {
                "telegram_id": 888,
                "full_name": "Parent Example",
                "role": "parent",
                "is_active": True,
            },
        }
        self.blocks = {}

    async def get_user(self, telegram_id):
        return self.users.get(telegram_id)

    async def is_telegram_id_blocked(self, telegram_id):
        return telegram_id in self.blocks

    async def block_telegram_id(self, telegram_id, blocked_by=None, reason=None):
        user = self.users.get(telegram_id)
        previous_is_active = user.get("is_active") if user else None
        self.blocks[telegram_id] = {
            "telegram_id": telegram_id,
            "reason": reason,
            "blocked_by": blocked_by,
            "previous_is_active": previous_is_active,
            "blocked_at": None,
        }
        if user:
            user["is_active"] = False
        return await self.get_telegram_block(telegram_id)

    async def get_telegram_block(self, telegram_id):
        block = self.blocks.get(telegram_id)
        if not block:
            return None
        user = self.users.get(telegram_id) or {}
        return {**block, **user}

    async def unblock_telegram_id(self, telegram_id):
        block = self.blocks.pop(telegram_id, None)
        if not block:
            return {"removed": False, "reactivated": False}
        reactivated = False
        if block.get("previous_is_active") is True and telegram_id in self.users:
            self.users[telegram_id]["is_active"] = True
            reactivated = True
        return {"removed": True, "reactivated": reactivated}

    async def get_blocked_telegram_ids(self, limit=20):
        items = []
        for telegram_id in list(self.blocks.keys())[:limit]:
            items.append(await self.get_telegram_block(telegram_id))
        return items


class AccessBlockMiddlewareTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.admin_id_backup = config.ADMIN_ID
        config.ADMIN_ID = 9001

    def tearDown(self):
        config.ADMIN_ID = self.admin_id_backup

    async def test_blocked_message_is_rejected_before_handler(self):
        db = _AccessDB(blocked_ids={111})
        middleware = DatabaseMiddleware(db)
        message = DummyMessage("/start", user_id=111)
        called = False

        async def handler(event, data):
            nonlocal called
            called = True
            return "ok"

        result = await middleware(handler, message, {})

        self.assertIsNone(result)
        self.assertFalse(called)
        self.assertEqual(message.answers[-1], BLOCKED_ACCOUNT_TEXT)

    async def test_blocked_callback_gets_alert(self):
        db = _AccessDB(blocked_ids={111})
        middleware = DatabaseMiddleware(db)
        callback = DummyCallbackQuery("homework", user_id=111)
        called = False

        async def handler(event, data):
            nonlocal called
            called = True
            return "ok"

        result = await middleware(handler, callback, {})

        self.assertIsNone(result)
        self.assertFalse(called)
        self.assertEqual(callback.answers[-1].text, BLOCKED_ACCOUNT_ALERT)
        self.assertTrue(callback.answers[-1].show_alert)

    async def test_admin_is_not_blocked_by_blacklist(self):
        db = _AccessDB(blocked_ids={9001})
        middleware = DatabaseMiddleware(db)
        message = DummyMessage("/admin", user_id=9001)
        called = False

        async def handler(event, data):
            nonlocal called
            called = True
            return "ok"

        result = await middleware(handler, message, {})

        self.assertEqual(result, "ok")
        self.assertTrue(called)


class AdminBlockCommandsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.admin_id_backup = config.ADMIN_ID
        config.ADMIN_ID = 9001

    def tearDown(self):
        config.ADMIN_ID = self.admin_id_backup

    async def test_block_command_blocks_existing_user_and_deactivates_profile(self):
        db = _AdminBlockDB()
        message = DummyMessage("/block 777 risk", user_id=9001, full_name="Admin")

        await command_block(message, db)

        self.assertIn(777, db.blocks)
        self.assertFalse(db.users[777]["is_active"])
        self.assertIn("<code>777</code>", message.answers[-1])
        self.assertIn("Ann Student", message.answers[-1])

    async def test_unblock_command_restores_profile_when_user_was_active(self):
        db = _AdminBlockDB()
        await db.block_telegram_id(777, blocked_by=9001, reason="risk")
        message = DummyMessage("/unblock 777", user_id=9001, full_name="Admin")

        await command_unblock(message, db)

        self.assertNotIn(777, db.blocks)
        self.assertTrue(db.users[777]["is_active"])
        self.assertIn("<code>777</code>", message.answers[-1])

    async def test_blocked_command_lists_ids(self):
        db = _AdminBlockDB()
        await db.block_telegram_id(777, blocked_by=9001, reason="risk")
        await db.block_telegram_id(999, blocked_by=9001, reason="spam")
        message = DummyMessage("/blocked", user_id=9001, full_name="Admin")

        await command_blocked(message, db)

        self.assertIn("<code>777</code>", message.answers[-1])
        self.assertIn("<code>999</code>", message.answers[-1])

    def test_service_menu_has_blocked_ids_entry(self):
        callbacks = [
            button.callback_data
            for row in admin_service_keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("admin:blocked", callbacks)

    async def test_blocked_callback_lists_ids_with_unblock_buttons(self):
        db = _AdminBlockDB()
        await db.block_telegram_id(777, blocked_by=9001, reason="risk")
        callback = DummyCallbackQuery("admin:blocked", user_id=9001)

        await admin_blocked(callback, db)

        self.assertIn("<code>777</code>", callback.message.edits[-1])
        markup = callback.message.reply_markups[-1]
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertIn("admin:blocked:add", callbacks)
        self.assertIn("admin:blocked:unblock:777", callbacks)
        self.assertIn("admin:cat:service", callbacks)

    async def test_blocked_unblock_callback_removes_block_and_returns_to_list(self):
        db = _AdminBlockDB()
        await db.block_telegram_id(777, blocked_by=9001, reason="risk")
        callback = DummyCallbackQuery("admin:blocked:unblock:777", user_id=9001)

        await admin_blocked_unblock(callback, db)

        self.assertNotIn(777, db.blocks)
        self.assertTrue(db.users[777]["is_active"])
        self.assertTrue(callback.message.edits)
        self.assertEqual(callback.answers[-1].text, "Блокировка снята.")

    async def test_blocked_add_flow_blocks_id_from_button_route(self):
        db = _AdminBlockDB()
        state = DummyState()
        callback = DummyCallbackQuery("admin:blocked:add", user_id=9001)

        await admin_blocked_add_start(callback, state)

        self.assertEqual(state.state, AdminBlockTelegramId.waiting_for_target)
        message = DummyMessage("999 spam", user_id=9001, full_name="Admin")

        await admin_blocked_add_text(message, state, db)

        self.assertIn(999, db.blocks)
        self.assertIsNone(state.state)
        self.assertIn("<code>999</code>", message.answers[-1])


if __name__ == "__main__":
    unittest.main()
