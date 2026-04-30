import sys
import json
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.db_api.admin_inbox import DatabaseAdminInboxMixin


class FakeDb(DatabaseAdminInboxMixin):
    def __init__(self):
        self._rows: list[dict] = []
        self._next_id = 1

    async def execute(self, command, *args, fetch=False, fetchval=False, fetchrow=False, execute=False):
        cmd = command.strip().upper()

        if "INSERT INTO ADMIN_INBOX" in cmd:
            kind = args[0]
            payload_str = args[1]
            row = {
                "id": self._next_id,
                "kind": kind,
                "payload": payload_str,
                "created_at": datetime.now(),
                "read_at": None,
                "handled_at": None,
                "handled_by": None,
            }
            self._rows.append(row)
            self._next_id += 1
            if fetchval:
                return row["id"]
            return None

        if "FROM ADMIN_INBOX" in cmd:
            if "WHERE ID = $1" in cmd:
                event_id = args[0]
                rows = [r for r in self._rows if r["id"] == event_id]
                if fetch:
                    return rows
                if fetchrow:
                    return rows[0] if rows else None
                if fetchval:
                    return rows[0]["id"] if rows else None
                return None

            if "COUNT(*)" in cmd:
                count = sum(1 for r in self._rows if r["handled_at"] is None)
                return count

            unread = [r for r in self._rows if r["handled_at"] is None]
            unread.sort(key=lambda r: r["created_at"], reverse=True)
            limit = args[0] if args else 20
            if fetch:
                return unread[:limit]
            return None

        if "UPDATE ADMIN_INBOX" in cmd:
            if "WHERE ID = $1" in cmd:
                event_id = args[0]
                handled_by = args[1]
                updated = 0
                for r in self._rows:
                    if r["id"] == event_id and r["handled_at"] is None:
                        r["handled_at"] = datetime.now()
                        r["handled_by"] = handled_by
                        r["read_at"] = r["read_at"] or datetime.now()
                        updated += 1
                return f"UPDATE {updated}"
            else:
                handled_by = args[0]
                updated = 0
                for r in self._rows:
                    if r["handled_at"] is None:
                        r["handled_at"] = datetime.now()
                        r["handled_by"] = handled_by
                        r["read_at"] = r["read_at"] or datetime.now()
                        updated += 1
                return f"UPDATE {updated}"

        return None


class AdminInboxMixinTest(unittest.IsolatedAsyncioTestCase):
    async def test_add_event_returns_positive_id(self):
        db = FakeDb()
        event_id = await db.add_inbox_event("reply", {"telegram_id": 1, "full_name": "Иван", "context": "homework", "message_preview": "Не понял задание"})
        self.assertGreater(event_id, 0)

    async def test_get_unread_returns_added_events(self):
        db = FakeDb()
        await db.add_inbox_event("reply", {"telegram_id": 1, "full_name": "Иван", "context": "homework", "message_preview": "Тест"})
        await db.add_inbox_event("freeze_request", {"telegram_id": 2, "full_name": "Маша", "context": "freeze", "message_preview": "Заморозка"})
        events = await db.get_unread_inbox(limit=20)
        self.assertEqual(len(events), 2)

    async def test_mark_inbox_read_removes_event_from_unread(self):
        db = FakeDb()
        event_id = await db.add_inbox_event("reply", {"telegram_id": 1, "full_name": "Иван", "context": "general", "message_preview": "Привет"})
        await db.mark_inbox_read(event_id, handled_by=999)
        events = await db.get_unread_inbox(limit=20)
        self.assertEqual(len(events), 0)

    async def test_mark_all_read_returns_count_and_clears_all(self):
        db = FakeDb()
        await db.add_inbox_event("reply", {"telegram_id": 1, "full_name": "А", "context": "general", "message_preview": ""})
        await db.add_inbox_event("freeze_request", {"telegram_id": 2, "full_name": "Б", "context": "freeze", "message_preview": ""})
        count = await db.mark_all_inbox_read(handled_by=999)
        self.assertEqual(count, 2)
        events = await db.get_unread_inbox(limit=20)
        self.assertEqual(len(events), 0)

    async def test_count_unread_inbox(self):
        db = FakeDb()
        await db.add_inbox_event("reply", {"telegram_id": 1, "full_name": "А", "context": "general", "message_preview": ""})
        await db.add_inbox_event("reply", {"telegram_id": 2, "full_name": "Б", "context": "homework", "message_preview": ""})
        count = await db.count_unread_inbox()
        self.assertEqual(count, 2)
        await db.mark_inbox_read(1, handled_by=999)
        count = await db.count_unread_inbox()
        self.assertEqual(count, 1)

    async def test_get_unread_respects_limit(self):
        db = FakeDb()
        for i in range(5):
            await db.add_inbox_event("reply", {"telegram_id": i, "full_name": f"User {i}", "context": "general", "message_preview": ""})
        events = await db.get_unread_inbox(limit=3)
        self.assertEqual(len(events), 3)


if __name__ == "__main__":
    unittest.main()
