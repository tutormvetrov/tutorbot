import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app import RateLimitMiddleware
from tests.helpers import DummyBot, DummyCallbackQuery, DummyMessage
from utils.telegram_actions import with_chat_action


class RateLimitMiddlewareTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_message_is_limited_after_first_action(self):
        now = [100.0]
        middleware = RateLimitMiddleware(
            user_seconds=0.7,
            admin_seconds=0.25,
            callback_seconds=0.5,
            admin_id=999,
            clock=lambda: now[0],
        )
        calls = []

        async def handler(event, data):
            calls.append(event)
            return "ok"

        message = DummyMessage(user_id=101)

        self.assertEqual(await middleware(handler, message, {}), "ok")
        self.assertIsNone(await middleware(handler, message, {}))

        self.assertEqual(len(calls), 1)
        self.assertEqual(message.answers[-1], "Подождите секунду.")

    async def test_admin_message_uses_shorter_limit(self):
        now = [100.0]
        middleware = RateLimitMiddleware(
            user_seconds=0.7,
            admin_seconds=0.25,
            callback_seconds=0.5,
            admin_id=42,
            clock=lambda: now[0],
        )
        calls = []

        async def handler(event, data):
            calls.append(event)
            return "ok"

        message = DummyMessage(user_id=42)

        await middleware(handler, message, {})
        now[0] += 0.3
        await middleware(handler, message, {})

        self.assertEqual(len(calls), 2)

    async def test_callback_limit_blocks_duplicate_button(self):
        now = [100.0]
        middleware = RateLimitMiddleware(
            user_seconds=0.7,
            admin_seconds=0.25,
            callback_seconds=0.5,
            admin_id=999,
            clock=lambda: now[0],
        )
        calls = []

        async def handler(event, data):
            calls.append(event.data)
            return "ok"

        callback = DummyCallbackQuery("payment_delete:101:55", user_id=101)

        await middleware(handler, callback, {})
        await middleware(handler, callback, {})

        self.assertEqual(calls, ["payment_delete:101:55"])
        self.assertEqual(callback.answers[-1].text, "Подождите секунду.")


class ChatActionHelperTest(unittest.IsolatedAsyncioTestCase):
    async def test_message_chat_action_is_sent_before_body(self):
        bot = DummyBot()
        message = DummyMessage(user_id=101, bot=bot)

        async with with_chat_action(message, "typing"):
            pass

        self.assertEqual(len(bot.chat_actions), 1)
        self.assertEqual(bot.chat_actions[0].chat_id, 101)
        self.assertEqual(bot.chat_actions[0].action, "typing")

    async def test_callback_chat_action_uses_message_chat(self):
        bot = DummyBot()
        callback = DummyCallbackQuery("admin:finance", bot=bot, user_id=101)

        async with with_chat_action(callback, "typing"):
            pass

        self.assertEqual(len(bot.chat_actions), 1)
        self.assertEqual(bot.chat_actions[0].chat_id, 101)

    async def test_chat_action_errors_do_not_break_body(self):
        class FailingBot(DummyBot):
            async def send_chat_action(self, chat_id, action):
                raise RuntimeError("telegram error")

        message = DummyMessage(user_id=101, bot=FailingBot())
        executed = False

        async with with_chat_action(message, "typing"):
            executed = True

        self.assertTrue(executed)
