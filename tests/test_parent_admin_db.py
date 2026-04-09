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
    def __init__(self):
        self.executed = []

    def transaction(self):
        return _Transaction()

    async def execute(self, query, *args):
        self.executed.append((query, args))
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


class _ExecuteDB(DatabaseUserMixin):
    def __init__(self):
        self.calls = []

    async def execute(self, command, *args, **kwargs):
        self.calls.append((command, args, kwargs))
        return "OK"


class _DeleteDB(DatabaseUserMixin):
    def __init__(self, conn):
        self.pool = _TxPool(conn)


class ParentAdminDBTest(unittest.IsolatedAsyncioTestCase):
    async def test_deactivate_parent_updates_only_parent_access(self):
        db = _ExecuteDB()

        await db.deactivate_parent(701)

        command, args, kwargs = db.calls[0]
        self.assertIn("UPDATE users", command)
        self.assertIn("role = 'parent'", command)
        self.assertEqual(args, (701,))
        self.assertTrue(kwargs["execute"])

    async def test_delete_parent_preserving_history_detaches_payments_and_links(self):
        conn = _TxConn()
        db = _DeleteDB(conn)

        await db.delete_parent_preserving_history(701)

        commands = [command for command, _ in conn.executed]
        args = [call_args for _, call_args in conn.executed]

        self.assertEqual(
            commands,
            [
                "UPDATE payments SET payer_id = NULL WHERE payer_id = $1",
                "DELETE FROM student_parent WHERE parent_id = $1",
                "DELETE FROM users WHERE telegram_id = $1 AND role = 'parent'",
            ],
        )
        self.assertEqual(args, [(701,), (701,), (701,)])


if __name__ == "__main__":
    unittest.main()
