class DatabaseWorkRulesMixin:

    async def get_work_rules(self, active_only: bool = True):
        condition = "WHERE is_active = true" if active_only else ""
        return await self.execute(
            f"""
            SELECT * FROM work_rules
            {condition}
            ORDER BY sort_order, id
            """,
            fetch=True,
        )

    async def get_work_rule_by_id(self, rule_id: int):
        return await self.execute(
            "SELECT * FROM work_rules WHERE id = $1",
            rule_id, fetchrow=True,
        )

    async def add_work_rule(self, title: str, body: str) -> int:
        max_order = await self.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM work_rules WHERE is_active = true",
            fetchval=True,
        )
        return await self.execute(
            """
            INSERT INTO work_rules (title, body, sort_order)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            title, body, (int(max_order or 0) + 1), fetchval=True,
        )

    async def update_work_rule(self, rule_id: int, *, title: str | None = None, body: str | None = None):
        if title is not None:
            await self.execute(
                "UPDATE work_rules SET title = $1 WHERE id = $2",
                title, rule_id, execute=True,
            )
        if body is not None:
            await self.execute(
                "UPDATE work_rules SET body = $1 WHERE id = $2",
                body, rule_id, execute=True,
            )

    async def delete_work_rule(self, rule_id: int):
        await self.execute(
            "UPDATE work_rules SET is_active = false WHERE id = $1",
            rule_id, execute=True,
        )

    async def set_rules_accepted(self, telegram_id: int):
        await self.execute(
            "UPDATE users SET rules_accepted_at = CURRENT_TIMESTAMP WHERE telegram_id = $1",
            telegram_id, execute=True,
        )
