import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.db_api.payments import DatabasePaymentMixin


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self):
        self.fetchval_calls = []
        self.execute_calls = []

    def transaction(self):
        return _Transaction()

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return 123

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "OK"


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


class _DB(DatabasePaymentMixin):
    def __init__(self, conn):
        self.pool = _Pool(conn)


class PaymentDBTest(unittest.IsolatedAsyncioTestCase):
    async def test_add_payment_can_record_parent_as_payer(self):
        conn = _Conn()
        db = _DB(conn)

        payment_id = await db.add_payment(707, 3000, 4, payer_id=960)

        self.assertEqual(payment_id, 123)
        query, args = conn.fetchval_calls[0]
        self.assertIn("(payer_id, student_id", query)
        self.assertEqual(args, (960, 707, 3000, 4))

    async def test_add_payment_marks_balance_transaction_as_payment_added(self):
        conn = _Conn()
        db = _DB(conn)

        await db.add_payment(707, 3000, 4)

        query, args = conn.execute_calls[0]
        self.assertIn("balance_transactions", query)
        self.assertIn("'payment_added'", query)
        self.assertEqual(args, (707, 4, 123))
