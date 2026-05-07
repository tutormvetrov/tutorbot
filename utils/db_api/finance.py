from datetime import datetime, timedelta


class DatabaseFinanceMixin:

    async def get_income_period(self, since: datetime) -> float:
        result = await self.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payments
            WHERE status = 'confirmed' AND payment_date >= $1
            """,
            since, fetchval=True,
        )
        return float(result or 0)

    async def get_payment_discipline(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE((
                    SELECT SUM(bt.amount_lessons)
                    FROM balance_transactions bt
                    WHERE bt.student_id = u.telegram_id
                ), 0)::int AS balance,
                (
                    SELECT MAX(bt.created_at)
                    FROM balance_transactions bt
                    WHERE bt.student_id = u.telegram_id
                      AND bt.type = 'payment_added'
                ) AS last_payment_at
            FROM users u
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            ORDER BY u.full_name
            """,
            fetch=True,
        )

    async def get_tariff_stats(self):
        return await self.execute(
            """
            SELECT
                lpr.id AS rate_id,
                lpr.label,
                lpr.group_size,
                lpr.duration_minutes,
                lpr.amount,
                lpr.currency,
                COUNT(u.telegram_id)::int AS student_count
            FROM lesson_pricing_rates lpr
            LEFT JOIN users u
              ON u.pricing_rate_id = lpr.id
             AND u.role = 'student'
             AND u.is_active = true
             AND COALESCE(u.is_internal_account, false) = false
            WHERE lpr.is_active = true
            GROUP BY lpr.id, lpr.label, lpr.group_size, lpr.duration_minutes, lpr.amount, lpr.currency
            ORDER BY lpr.group_size, lpr.duration_minutes
            """,
            fetch=True,
        )

    async def get_forecast_data(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(lpr.amount, 0) AS rate_amount,
                COALESCE(u.lessons_per_week, 1)::int AS lessons_per_week,
                (
                    SELECT COUNT(*)::int
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.status = 'completed'
                      AND l.lesson_date >= NOW() - INTERVAL '28 days'
                ) AS lessons_28d,
                (
                    SELECT COUNT(*)::int
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.lesson_date >= NOW() - INTERVAL '28 days'
                      AND (l.status = 'cancelled' OR l.is_no_show = true)
                ) AS lost_28d
            FROM users u
            LEFT JOIN lesson_pricing_rates lpr ON lpr.id = u.pricing_rate_id AND lpr.is_active = true
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            ORDER BY u.full_name
            """,
            fetch=True,
        )
