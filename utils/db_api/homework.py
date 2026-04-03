class DatabaseHomeworkMixin:
    async def add_homework(self, student_id: int, title: str, description: str, deadline):
        return await self.execute(
            """
            INSERT INTO homework (student_id, title, description, deadline)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            student_id, title, description, deadline, fetchval=True,
        )

    async def get_student_homework(self, student_id: int, status: str = None):
        if status:
            return await self.execute(
                "SELECT * FROM homework WHERE student_id=$1 AND status=$2 ORDER BY deadline ASC",
                student_id, status, fetch=True,
            )
        return await self.execute(
            "SELECT * FROM homework WHERE student_id=$1 ORDER BY deadline ASC",
            student_id, fetch=True,
        )

    async def get_homework_by_id(self, hw_id: int):
        return await self.execute(
            "SELECT * FROM homework WHERE id=$1", hw_id, fetchrow=True,
        )

    async def delete_homework(self, hw_id: int):
        await self.execute(
            "DELETE FROM homework WHERE id=$1", hw_id, execute=True,
        )

    async def mark_homework_done(self, hw_id: int, student_id: int):
        await self.execute(
            "UPDATE homework SET status='done' WHERE id=$1 AND student_id=$2 AND status='active'",
            hw_id, student_id, execute=True,
        )

    async def get_homework_due_tomorrow(self):
        return await self.execute(
            """
            SELECT h.*, u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal') AS speech_style
            FROM homework h
            JOIN users u ON u.telegram_id = h.student_id
            WHERE h.status = 'active'
              AND h.reminder_sent = false
              AND h.deadline >= NOW() + INTERVAL '20 hours'
              AND h.deadline <= NOW() + INTERVAL '28 hours'
            """,
            fetch=True,
        )

    async def mark_homework_reminder_sent(self, hw_id: int):
        await self.execute(
            "UPDATE homework SET reminder_sent=true WHERE id=$1", hw_id, execute=True,
        )

    async def get_all_active_homework(self):
        return await self.execute(
            """
            SELECT h.*, u.full_name
            FROM homework h
            JOIN users u ON u.telegram_id = h.student_id
            WHERE h.status = 'active'
            ORDER BY h.deadline ASC
            """,
            fetch=True,
        )
