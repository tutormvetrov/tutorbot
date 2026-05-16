import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin_sections.finance import (
    admin_finance_balances,
    admin_finance_payment_inbox,
    admin_finance_unpaid,
)
from tests.helpers import DummyCallbackQuery, DummyMessage


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class FinancePanelTest(unittest.IsolatedAsyncioTestCase):
    async def test_payment_inbox_filters_payment_events(self):
        class FakeDB:
            async def get_unread_inbox(self, limit=30):
                return [
                    {
                        "id": 1,
                        "kind": "reply",
                        "payload": {"context": "payment", "full_name": "Мария", "message_preview": "Оплатила"},
                        "created_at": datetime.now(),
                        "handled_at": None,
                    },
                    {
                        "id": 2,
                        "kind": "reply",
                        "payload": {"context": "homework", "full_name": "Иван", "message_preview": "ДЗ"},
                        "created_at": datetime.now(),
                        "handled_at": None,
                    },
                ]

        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery("admin:finance:payment_inbox", message=message, user_id=config.ADMIN_ID)

        await admin_finance_payment_inbox(callback, FakeDB())

        callbacks = _callbacks(message.reply_markups[-1])
        self.assertIn("admin:finance:inbox:item:1", callbacks)
        self.assertNotIn("admin:finance:inbox:item:2", callbacks)
        self.assertIn("Входящие оплаты", message.edits[-1])
        self.assertIn("admin:finance", callbacks)

    async def test_balances_screen_opens_student_payment_management(self):
        class FakeDB:
            async def get_students_with_balances(self):
                return [
                    {"telegram_id": 707, "full_name": "Анна", "lesson_balance": 0},
                    {"telegram_id": 808, "full_name": "Иван", "lesson_balance": 3},
                ]

        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery("admin:finance:balances", message=message, user_id=config.ADMIN_ID)

        await admin_finance_balances(callback, FakeDB())

        callbacks = _callbacks(message.reply_markups[-1])
        self.assertIn("admin:student_payments:707:0:finance", callbacks)
        self.assertIn("admin:student_payments:808:0:finance", callbacks)
        self.assertIn("admin:finance", callbacks)

    async def test_unpaid_screen_shows_only_zero_or_negative_balances(self):
        class FakeDB:
            async def get_students_with_balances(self):
                return [
                    {"telegram_id": 707, "full_name": "Анна", "lesson_balance": 0},
                    {"telegram_id": 808, "full_name": "Иван", "lesson_balance": 2},
                ]

        message = DummyMessage(user_id=config.ADMIN_ID)
        callback = DummyCallbackQuery("admin:finance:unpaid", message=message, user_id=config.ADMIN_ID)

        await admin_finance_unpaid(callback, FakeDB())

        callbacks = _callbacks(message.reply_markups[-1])
        self.assertIn("admin:student_payments:707:0:finance", callbacks)
        self.assertNotIn("admin:student_payments:808:0:finance", callbacks)
        self.assertIn("admin:finance", callbacks)
