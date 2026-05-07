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
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM balance_transactions WHERE payment_id = $1",
                    payment_id,
                )
                await conn.execute(
                    "DELETE FROM payments WHERE id = $1",
                    payment_id,
                )

    async def add_payment(self, student_id: int, amount: float, lessons_count: int) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                payment_id = await conn.fetchval(
                    """
                    INSERT INTO payments
                        (payer_id, student_id, amount, lessons_count, lessons_remaining, status, payment_date)
                    VALUES ($1, $1, $2, $3, $3, 'confirmed', CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    student_id, amount, lessons_count,
                )
                await conn.execute(
                    """
                    INSERT INTO balance_transactions
                        (student_id, type, amount_lessons, payment_id)
                    VALUES ($1, 'payment_added', $2, $3)
                    """,
                    student_id, lessons_count, payment_id,
                )
                return payment_id
