from typing import Optional

from utils.time import business_naive_now


class DatabaseLessonMixin:
    async def get_lessons_for_reminder(self):
        return await self.execute(
            """
            SELECT
                l.*,
                u.telegram_id,
                u.full_name,
                u.lesson_reminders,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.speech_style, 'formal') AS speech_style
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.status = 'active'
              AND l.reminder_sent = false
              AND (u.lesson_reminders = 'enabled'
                   OR u.lesson_reminders LIKE 'paused_until:%')
              AND (
                  (
                      COALESCE(u.lesson_format, 'online') != 'offline'
                      AND l.lesson_date >= NOW()
                      AND l.lesson_date <= NOW() + INTERVAL '15 minutes'
                  )
                  OR
                  (
                      COALESCE(u.lesson_format, 'online') = 'offline'
                      AND l.lesson_date >= NOW() + INTERVAL '45 minutes'
                      AND l.lesson_date <= NOW() + INTERVAL '60 minutes'
                  )
              )
            """,
            fetch=True,
        )

    async def get_lessons_for_teacher_followup(self):
        return await self.execute(
            """
            SELECT
                l.id,
                l.student_id,
                l.lesson_date,
                l.status,
                u.full_name,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.lesson_duration_minutes, 90) AS lesson_duration_minutes
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.lesson_date IS NOT NULL
              AND l.status IN ('active', 'completed')
              AND COALESCE(l.teacher_followup_sent, false) = false
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
              AND l.lesson_date + (COALESCE(u.lesson_duration_minutes, 90) * INTERVAL '1 minute') <= NOW()
            ORDER BY l.lesson_date ASC
            """,
            fetch=True,
        )

    async def mark_teacher_followup_sent(self, lesson_id: int):
        await self.execute(
            "UPDATE lessons SET teacher_followup_sent = true WHERE id = $1",
            lesson_id,
            execute=True,
        )

    async def get_lessons_for_teacher_bookmark_reminder(self):
        return await self.execute(
            """
            SELECT
                l.id,
                l.student_id,
                l.lesson_date,
                u.full_name,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.current_bookmark_state, 'empty') AS current_bookmark_state,
                u.current_bookmark_text,
                u.current_bookmark_updated_at,
                u.current_bookmark_lesson_id
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.status = 'active'
              AND l.lesson_date IS NOT NULL
              AND COALESCE(l.teacher_pre_lesson_note_sent, false) = false
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
              AND (
                  (
                      COALESCE(u.lesson_format, 'online') != 'offline'
                      AND l.lesson_date >= NOW()
                      AND l.lesson_date <= NOW() + INTERVAL '30 minutes'
                  )
                  OR
                  (
                      COALESCE(u.lesson_format, 'online') = 'offline'
                      AND l.lesson_date >= NOW() + INTERVAL '45 minutes'
                      AND l.lesson_date <= NOW() + INTERVAL '60 minutes'
                  )
              )
            ORDER BY l.lesson_date ASC
            """,
            fetch=True,
        )

    async def mark_teacher_pre_lesson_note_sent(self, lesson_id: int):
        await self.execute(
            "UPDATE lessons SET teacher_pre_lesson_note_sent = true WHERE id = $1",
            lesson_id,
            execute=True,
        )

    async def get_lesson_context(self, lesson_id: int):
        return await self.execute(
            """
            SELECT
                l.id,
                l.student_id,
                l.lesson_date,
                l.teacher_comment,
                u.full_name,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.current_bookmark_state, 'empty') AS current_bookmark_state,
                u.current_bookmark_text,
                COALESCE(u.lesson_duration_minutes, 90) AS lesson_duration_minutes
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.id = $1
            """,
            lesson_id,
            fetchrow=True,
        )

    async def save_teacher_comment(self, lesson_id: int, comment_text: str):
        await self.execute(
            """
            UPDATE lessons
            SET teacher_comment = $2,
                teacher_comment_saved_at = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            lesson_id,
            comment_text,
            execute=True,
        )

    async def mark_lesson_reminder_sent(self, lesson_id: int):
        await self.execute(
            "UPDATE lessons SET reminder_sent=true WHERE id=$1", lesson_id, execute=True,
        )

    async def get_lessons_missing_homework(self):
        return await self.execute(
            """
            WITH next_lessons AS (
                SELECT DISTINCT ON (l.student_id)
                    l.id,
                    l.student_id,
                    l.lesson_date,
                    u.full_name
                FROM lessons l
                JOIN users u ON u.telegram_id = l.student_id
                WHERE l.status = 'active'
                  AND l.lesson_date IS NOT NULL
                  AND l.homework_check_reminder_sent = false
                  AND l.lesson_date > NOW()
                  AND l.lesson_date <= NOW() + INTERVAL '24 hours'
                  AND u.role = 'student'
                  AND u.is_active = true
                  AND COALESCE(u.is_internal_account, false) = false
                ORDER BY l.student_id, l.lesson_date ASC
            ),
            previous_lessons AS (
                SELECT
                    n.id AS next_lesson_id,
                    MAX(l.lesson_date) AS previous_lesson_date
                FROM next_lessons n
                JOIN lessons l ON l.student_id = n.student_id
                WHERE l.lesson_date IS NOT NULL
                  AND l.lesson_date < n.lesson_date
                  AND l.status IN ('active', 'completed')
                GROUP BY n.id
            )
            SELECT
                n.id,
                n.student_id,
                n.lesson_date,
                n.full_name,
                p.previous_lesson_date
            FROM next_lessons n
            JOIN previous_lessons p ON p.next_lesson_id = n.id
            WHERE NOT EXISTS (
                SELECT 1
                FROM homework h
                WHERE h.student_id = n.student_id
                  AND h.created_at >= p.previous_lesson_date
                  AND h.created_at <= n.lesson_date
            )
            ORDER BY n.lesson_date ASC
            """,
            fetch=True,
        )

    async def mark_homework_check_reminder_sent(self, lesson_id: int):
        await self.execute(
            "UPDATE lessons SET homework_check_reminder_sent = true WHERE id = $1",
            lesson_id,
            execute=True,
        )

    async def set_lesson_reminders(self, telegram_id: int, value: str):
        await self.execute(
            "UPDATE users SET lesson_reminders=$1 WHERE telegram_id=$2",
            value, telegram_id, execute=True,
        )

    async def set_lesson_format(self, telegram_id: int, value: str):
        await self.execute(
            "UPDATE users SET lesson_format=$1 WHERE telegram_id=$2",
            value, telegram_id, execute=True,
        )

    async def get_active_lessons(self, student_id: int):
        return await self.execute(
            """
            SELECT l.*, COALESCE(u.lesson_format, 'online') AS lesson_format
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.student_id = $1 AND l.status = 'active'
            ORDER BY lesson_date ASC NULLS LAST, created_at DESC
            """,
            student_id, fetch=True,
        )

    async def get_pending_freeze_lessons(self):
        return await self.execute(
            """
            SELECT l.*, u.full_name, u.telegram_id AS user_telegram_id
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.status = 'freeze_pending'
            ORDER BY l.created_at ASC
            """,
            fetch=True,
        )

    async def add_lesson(self, student_id: int, lesson_date, google_event_id: Optional[str] = None):
        await self.execute(
            """
            INSERT INTO lessons (student_id, lesson_date, google_event_id, status, source)
            VALUES ($1, $2, $3, 'active', 'manual')
            """,
            student_id, lesson_date, google_event_id, execute=True,
        )
        if lesson_date is not None:
            await self._touch_cached_first_lesson_date(student_id, lesson_date)

    async def _touch_cached_first_lesson_date(self, student_id: int, lesson_date):
        await self.execute(
            """
            UPDATE users
            SET cached_first_lesson_date = CASE
                WHEN cached_first_lesson_date IS NULL THEN $2
                WHEN $2 < cached_first_lesson_date THEN $2
                ELSE cached_first_lesson_date
            END
            WHERE telegram_id = $1
            """,
            student_id, lesson_date, execute=True,
        )

    async def upsert_lesson_from_calendar(self, student_id: int, google_event_id: str, lesson_date):
        existing = await self.execute(
            "SELECT id, lesson_date FROM lessons WHERE google_event_id = $1",
            google_event_id, fetchrow=True,
        )
        if existing:
            await self.execute(
                """
                UPDATE lessons
                SET lesson_date = $2,
                    student_id = $3,
                    reminder_sent = CASE
                        WHEN lesson_date IS DISTINCT FROM $2 THEN false
                        ELSE reminder_sent
                    END,
                    homework_check_reminder_sent = CASE
                        WHEN lesson_date IS DISTINCT FROM $2 THEN false
                        ELSE homework_check_reminder_sent
                    END,
                    teacher_followup_sent = CASE
                        WHEN lesson_date IS DISTINCT FROM $2 THEN false
                        ELSE teacher_followup_sent
                    END,
                    teacher_pre_lesson_note_sent = CASE
                        WHEN lesson_date IS DISTINCT FROM $2 THEN false
                        ELSE teacher_pre_lesson_note_sent
                    END,
                    status = 'active',
                    source = 'calendar'
                WHERE google_event_id = $1
                """,
                google_event_id, lesson_date, student_id, execute=True,
            )
            return "updated"

        await self.execute(
            """
            INSERT INTO lessons (student_id, google_event_id, lesson_date, status, source)
            VALUES ($1, $2, $3, 'active', 'calendar')
            """,
            student_id, google_event_id, lesson_date, execute=True,
        )
        if lesson_date is not None:
            await self._touch_cached_first_lesson_date(student_id, lesson_date)
        return "inserted"

    async def approve_freeze(self, lesson_id: int):
        await self.execute(
            """
            UPDATE lessons
            SET status = 'frozen', freeze_start_date = CURRENT_TIMESTAMP
            WHERE id = $1
            """,
            lesson_id, execute=True,
        )

    async def reject_freeze(self, lesson_id: int):
        await self.execute(
            """
            UPDATE lessons
            SET status = 'active',
                freeze_reason = NULL,
                freeze_start_date = NULL
            WHERE id = $1
            """,
            lesson_id, execute=True,
        )

    async def get_student_lesson_balance(self, student_id: int) -> int:
        result = await self.execute(
            """
            SELECT COALESCE(SUM(lessons_remaining), 0)
            FROM payments
            WHERE student_id = $1 AND status = 'confirmed'
            """,
            student_id, fetchval=True,
        )
        return int(result) if result else 0

    async def get_past_unprocessed_lessons(self):
        return await self.execute(
            """
            SELECT l.id, l.student_id
            FROM lessons l
            WHERE l.status = 'active'
              AND l.balance_consumed = false
              AND l.lesson_date IS NOT NULL
              AND l.lesson_date < NOW()
            """,
            fetch=True,
        )

    async def complete_lesson(self, lesson_id: int, student_id: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                lesson = await conn.fetchrow(
                    "SELECT lesson_date FROM lessons WHERE id = $1",
                    lesson_id,
                )
                await conn.execute(
                    """
                    UPDATE lessons
                    SET status = 'completed', balance_consumed = true
                    WHERE id = $1
                    """,
                    lesson_id,
                )
                payment = await conn.fetchrow(
                    """
                    SELECT id FROM payments
                    WHERE student_id = $1
                      AND status = 'confirmed'
                      AND lessons_remaining > 0
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    student_id,
                )
                if payment:
                    await conn.execute(
                        "UPDATE payments SET lessons_remaining = lessons_remaining - 1 WHERE id = $1",
                        payment['id'],
                    )
                lesson_date = lesson["lesson_date"] if lesson else None
                await conn.execute(
                    """
                    UPDATE users
                    SET lessons_completed_count = COALESCE(lessons_completed_count, 0) + 1,
                        cached_first_lesson_date = CASE
                            WHEN cached_first_lesson_date IS NULL THEN $2
                            WHEN $2 IS NOT NULL AND $2 < cached_first_lesson_date THEN $2
                            ELSE cached_first_lesson_date
                        END
                    WHERE telegram_id = $1
                    """,
                    student_id,
                    lesson_date,
                )

    async def delete_lesson(self, lesson_id: int):
        await self.execute(
            "DELETE FROM lessons WHERE id = $1", lesson_id, execute=True,
        )

    async def get_non_completed_lessons(self, student_id: int):
        return await self.execute(
            """
            SELECT * FROM lessons
            WHERE student_id = $1 AND status != 'completed'
            ORDER BY lesson_date ASC NULLS LAST
            """,
            student_id, fetch=True,
        )

    async def get_lessons_in_window(self, start_dt, end_dt):
        return await self.execute(
            """
            SELECT id, student_id, lesson_date, status
            FROM lessons
            WHERE lesson_date IS NOT NULL
              AND lesson_date >= $1
              AND lesson_date < $2
              AND status IN ('active', 'completed', 'freeze_pending')
            ORDER BY lesson_date ASC
            """,
            start_dt,
            end_dt,
            fetch=True,
        )

    async def get_google_event_ids_in_window(self, days_ahead: int = 60) -> list:
        from datetime import timedelta

        now = business_naive_now()
        end = now + timedelta(days=days_ahead)
        rows = await self.execute(
            """
            SELECT google_event_id FROM lessons
            WHERE status != 'completed'
              AND source = 'calendar'
              AND google_event_id IS NOT NULL
              AND lesson_date BETWEEN $1 AND $2
            """,
            now, end, fetch=True,
        )
        return [r['google_event_id'] for r in rows]

    async def delete_lessons_by_event_ids(self, event_ids: list):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM lessons WHERE source = 'calendar' AND google_event_id = ANY($1::text[])",
                event_ids,
            )
