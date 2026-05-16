import sys
from pathlib import Path
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.scheduler import payment_reminder_job, setup_scheduler


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append(SimpleNamespace(chat_id=chat_id, text=text, reply_markup=reply_markup))


class PaymentReminderSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def test_negative_and_zero_balances_are_unpaid(self):
        class FakeDB:
            async def get_students_with_balances(self):
                return [
                    {"telegram_id": 101, "full_name": "Минус", "lesson_balance": -1, "speech_style": "formal"},
                    {"telegram_id": 102, "full_name": "Ноль", "lesson_balance": 0, "speech_style": "formal"},
                    {"telegram_id": 103, "full_name": "Плюс", "lesson_balance": 2, "speech_style": "formal"},
                ]

        bot = FakeBot()

        await payment_reminder_job(bot, FakeDB(), "evening")

        student_chats = [message.chat_id for message in bot.messages if message.chat_id != 0]
        summary = bot.messages[-1].text
        self.assertIn(101, student_chats)
        self.assertIn(102, student_chats)
        self.assertNotIn(103, student_chats)
        self.assertIn("Не оплатили (2)", summary)
        self.assertIn("Оплатили (1)", summary)


class PaymentSchedulerSafetyTest(unittest.IsolatedAsyncioTestCase):
    def test_weekly_balance_reset_runs_after_evening_payment_reminder(self):
        scheduler = setup_scheduler(FakeBot(), object())
        reset_trigger = str(scheduler.get_job("weekly_balance_reset").trigger)
        evening_trigger = str(scheduler.get_job("payment_reminder_evening").trigger)

        self.assertIn("hour='22', minute='5'", reset_trigger)
        self.assertIn("hour='22', minute='0'", evening_trigger)

    async def test_weekly_balance_reset_skips_sunday_payments_for_next_week(self):
        from utils.scheduler import weekly_balance_reset_job

        class FakeDB:
            def __init__(self):
                self.sql = ""

            async def execute(self, sql, *args, **kwargs):
                self.sql = sql
                return []

        db = FakeDB()

        await weekly_balance_reset_job(FakeBot(), db)

        self.assertIn("bt.type = 'payment_added'", db.sql)
        self.assertIn("created_at AT TIME ZONE 'Europe/Moscow'", db.sql)
        self.assertIn("date_trunc('day', NOW() AT TIME ZONE 'Europe/Moscow')", db.sql)
