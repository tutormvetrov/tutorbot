from __future__ import annotations

from utils.resource_provider import detect_provider


class DatabaseStudentResourcesMixin:
    async def add_student_resource(
        self,
        *,
        student_id: int | None,
        label: str,
        url: str,
        is_primary: bool = False,
        created_by: int | None = None,
    ) -> int:
        provider = detect_provider(url)
        sort_order = await self.execute(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1
            FROM student_resources
            WHERE student_id IS NOT DISTINCT FROM $1
            """,
            student_id,
            fetchval=True,
        )
        if is_primary:
            await self.execute(
                """
                UPDATE student_resources
                SET is_primary = FALSE
                WHERE student_id IS NOT DISTINCT FROM $1 AND is_primary = TRUE
                """,
                student_id,
                execute=True,
            )
        new_id = await self.execute(
            """
            INSERT INTO student_resources
                (student_id, label, url, provider, is_primary, sort_order, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            student_id,
            label,
            url,
            provider,
            is_primary,
            int(sort_order or 0),
            created_by,
            fetchval=True,
        )
        return int(new_id)

    async def delete_student_resource(self, resource_id: int) -> bool:
        result = await self.execute(
            "DELETE FROM student_resources WHERE id = $1",
            resource_id,
            execute=True,
        )
        try:
            return int((result or "DELETE 0").split()[-1]) > 0
        except Exception:
            return False

    async def set_resource_primary(self, resource_id: int) -> bool:
        row = await self.execute(
            "SELECT student_id FROM student_resources WHERE id = $1",
            resource_id,
            fetchrow=True,
        )
        if not row:
            return False
        student_id = row["student_id"]
        await self.execute(
            """
            UPDATE student_resources
            SET is_primary = (id = $2)
            WHERE student_id IS NOT DISTINCT FROM $1
            """,
            student_id,
            resource_id,
            execute=True,
        )
        return True

    async def get_resource(self, resource_id: int) -> dict | None:
        row = await self.execute(
            """
            SELECT id, student_id, label, url, provider, is_primary, sort_order, created_at, created_by
            FROM student_resources
            WHERE id = $1
            """,
            resource_id,
            fetchrow=True,
        )
        return dict(row) if row else None

    async def list_student_resources(
        self,
        student_id: int | None,
        *,
        include_global: bool = True,
    ) -> list[dict]:
        if student_id is None:
            rows = await self.execute(
                """
                SELECT id, student_id, label, url, provider, is_primary, sort_order, created_at
                FROM student_resources
                WHERE student_id IS NULL
                ORDER BY is_primary DESC, sort_order, id
                """,
                fetch=True,
            )
        elif include_global:
            rows = await self.execute(
                """
                SELECT id, student_id, label, url, provider, is_primary, sort_order, created_at
                FROM student_resources
                WHERE student_id = $1 OR student_id IS NULL
                ORDER BY (student_id IS NULL), is_primary DESC, sort_order, id
                """,
                student_id,
                fetch=True,
            )
        else:
            rows = await self.execute(
                """
                SELECT id, student_id, label, url, provider, is_primary, sort_order, created_at
                FROM student_resources
                WHERE student_id = $1
                ORDER BY is_primary DESC, sort_order, id
                """,
                student_id,
                fetch=True,
            )
        return [dict(r) for r in (rows or [])]

    async def list_global_resources(self) -> list[dict]:
        return await self.list_student_resources(None, include_global=False)

    async def update_student_resource_label(self, resource_id: int, label: str) -> bool:
        result = await self.execute(
            "UPDATE student_resources SET label = $2 WHERE id = $1",
            resource_id,
            label,
            execute=True,
        )
        try:
            return int((result or "UPDATE 0").split()[-1]) > 0
        except Exception:
            return False
