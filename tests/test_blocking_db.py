import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.db_api.users import DatabaseUserMixin


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TxConn:
    def __init__(self, user_row=None, block_row=None, update_result="UPDATE 1"):
        self.user_row = user_row
        self.block_row = block_row
        self.update_result = update_result
        self.executed = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        if "FROM users" in query:
            return self.user_row
        if "FROM blocked_telegram_ids" in query:
            return self.block_row
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "UPDATE users" in query and "SET is_active = true" in query:
            return self.update_result
        return "OK"


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TxPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


class _BlockDB(DatabaseUserMixin):
    def __init__(self, conn):
        self.pool = _TxPool(conn)

    async def get_telegram_block(self, telegram_id):
        return {"telegram_id": telegram_id}


class BlockingDbTest(unittest.IsolatedAsyncioTestCase):
    async def test_block_telegram_id_saves_block_and_deactivates_existing_user(self):
        conn = _TxConn(user_row={"telegram_id": 701, "is_active": True})
        db = _BlockDB(conn)

        await db.block_telegram_id(701, blocked_by=9001, reason="risk")

        commands = [command for command, _ in conn.executed]
        args = [call_args for _, call_args in conn.executed]

        self.assertIn("FROM users", commands[0])
        self.assertIn("INSERT INTO blocked_telegram_ids", commands[1])
        self.assertIn("UPDATE users SET is_active = false", commands[2])
        self.assertEqual(args[0], (701,))
        self.assertEqual(args[1], (701, "risk", 9001, True))
        self.assertEqual(args[2], (701,))

    async def test_unblock_telegram_id_removes_block_and_reactivates_profile(self):
        conn = _TxConn(block_row={"previous_is_active": True})
        db = _BlockDB(conn)

        result = await db.unblock_telegram_id(701)

        commands = [command for command, _ in conn.executed]
        args = [call_args for _, call_args in conn.executed]

        self.assertEqual(result, {"removed": True, "reactivated": True})
        self.assertIn("SELECT previous_is_active", commands[0])
        self.assertEqual(commands[1], "DELETE FROM blocked_telegram_ids WHERE telegram_id = $1")
        self.assertIn("UPDATE users", commands[2])
        self.assertEqual(args[0], (701,))
        self.assertEqual(args[1], (701,))
        self.assertEqual(args[2], (701,))


if __name__ == "__main__":
    unittest.main()
