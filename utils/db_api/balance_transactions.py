from datetime import datetime


class DatabaseBalanceTransactionsMixin:

    async def add_balance_transaction(
        self,
        student_id: int,
        tx_type: str,
        amount_lessons: int,
        payment_id: int | None = None,
        lesson_id: int | None = None,
        note: str | None = None,
    ) -> int:
        return await self.execute(
            """
            INSERT INTO balance_transactions
                (student_id, type, amount_lessons, payment_id, lesson_id, note)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            student_id, tx_type, amount_lessons, payment_id, lesson_id, note,
            fetchval=True,
        )

    async def writeoff_negative_balance(
        self,
        student_id: int,
        note: str,
    ) -> int | None:
        """DEPRECATED-name: обнуляет любой ненулевой баланс одной транзакцией.

        Имя сохранено для обратной совместимости. Возвращает знаковое значение
        компенсирующей транзакции (например ``-5`` для `+5` баланса, ``+3`` для
        ``-3`` баланса) либо ``None``, если баланс уже равен нулю.
        """
        return await self.reset_balance_to_zero(student_id, note)

    async def reset_balance_to_zero(
        self,
        student_id: int,
        note: str,
    ) -> int | None:
        """Обнулить баланс ученика любого знака.

        Создаёт компенсирующую `admin_writeoff`-транзакцию на ``-balance``.
        Возвращает значение компенсации (signed) либо ``None``, если уже 0.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(SUM(amount_lessons), 0)::int AS balance
                    FROM balance_transactions
                    WHERE student_id = $1
                    """,
                    student_id,
                )
                balance = int(row["balance"]) if row else 0
                if balance == 0:
                    return None
                amount = -balance  # знак противоположный текущему балансу
                await conn.execute(
                    """
                    INSERT INTO balance_transactions
                        (student_id, type, amount_lessons, note)
                    VALUES ($1, 'admin_writeoff', $2, $3)
                    """,
                    student_id, amount, note,
                )
                return amount

    async def get_student_transactions(self, student_id: int, limit: int = 15):
        return await self.execute(
            """
            SELECT
                bt.*,
                p.amount AS payment_amount
            FROM balance_transactions bt
            LEFT JOIN payments p ON p.id = bt.payment_id
            WHERE bt.student_id = $1
            ORDER BY bt.created_at DESC
            LIMIT $2
            """,
            student_id, limit, fetch=True,
        )

    async def get_students_balance_map(self) -> dict[int, int]:
        rows = await self.execute(
            """
            SELECT student_id, COALESCE(SUM(amount_lessons), 0)::int AS balance
            FROM balance_transactions
            GROUP BY student_id
            """,
            fetch=True,
        )
        return {r["student_id"]: r["balance"] for r in (rows or [])}

    async def get_last_payment_dates(self) -> dict[int, "datetime"]:
        rows = await self.execute(
            """
            SELECT student_id, MAX(created_at) AS last_payment_at
            FROM balance_transactions
            WHERE type = 'payment_added'
            GROUP BY student_id
            """,
            fetch=True,
        )
        return {r["student_id"]: r["last_payment_at"] for r in (rows or [])}
