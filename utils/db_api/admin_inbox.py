from __future__ import annotations

import json
from datetime import datetime


class DatabaseAdminInboxMixin:
    async def add_inbox_event(self, kind: str, payload: dict) -> int:
        event_id = await self.execute(
            """
            INSERT INTO admin_inbox (kind, payload)
            VALUES ($1, $2::jsonb)
            RETURNING id
            """,
            kind,
            json.dumps(payload, ensure_ascii=False, default=str),
            fetchval=True,
        )
        return int(event_id)

    async def get_unread_inbox(self, limit: int = 20) -> list:
        return await self.execute(
            """
            SELECT id, kind, payload, created_at, read_at, handled_at, handled_by
            FROM admin_inbox
            WHERE handled_at IS NULL
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
            fetch=True,
        )

    async def get_inbox_event(self, event_id: int):
        return await self.execute(
            """
            SELECT id, kind, payload, created_at, read_at, handled_at, handled_by
            FROM admin_inbox
            WHERE id = $1
            """,
            event_id,
            fetchrow=True,
        )

    async def mark_inbox_read(self, event_id: int, handled_by: int) -> None:
        await self.execute(
            """
            UPDATE admin_inbox
            SET handled_at = now(),
                handled_by = $2,
                read_at = COALESCE(read_at, now())
            WHERE id = $1
              AND handled_at IS NULL
            """,
            event_id,
            handled_by,
            execute=True,
        )

    async def mark_all_inbox_read(self, handled_by: int) -> int:
        result = await self.execute(
            """
            UPDATE admin_inbox
            SET handled_at = now(),
                handled_by = $1,
                read_at = COALESCE(read_at, now())
            WHERE handled_at IS NULL
            """,
            handled_by,
            execute=True,
        )
        try:
            return int((result or "UPDATE 0").split()[-1])
        except Exception:
            return 0

    async def count_unread_inbox(self) -> int:
        result = await self.execute(
            """
            SELECT COUNT(*)::int
            FROM admin_inbox
            WHERE handled_at IS NULL
            """,
            fetchval=True,
        )
        return int(result or 0)
