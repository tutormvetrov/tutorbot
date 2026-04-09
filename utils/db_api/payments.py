class DatabasePaymentMixin:
    async def get_student_payments(self, payer_id: int, limit: int = 5):
        return await self.execute(
            """
            SELECT * FROM payments
            WHERE payer_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            payer_id, limit, fetch=True,
        )

    async def get_payments_for_student(self, student_id: int, limit: int = 5):
        return await self.execute(
            """
            SELECT * FROM payments
            WHERE student_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            student_id, limit, fetch=True,
        )

    async def get_payment_by_id(self, payment_id: int):
        return await self.execute(
            "SELECT * FROM payments WHERE id = $1", payment_id, fetchrow=True,
        )

    async def delete_payment(self, payment_id: int):
        await self.execute(
            "DELETE FROM payments WHERE id = $1", payment_id, execute=True,
        )

    async def add_payment(self, student_id: int, amount: float, lessons_count: int):
        return await self.execute(
            """
            INSERT INTO payments
                (payer_id, student_id, amount, lessons_count, lessons_remaining, status, payment_date)
            VALUES ($1, $1, $2, $3, $3, 'confirmed', CURRENT_TIMESTAMP)
            RETURNING id
            """,
            student_id, amount, lessons_count, fetchval=True,
        )
