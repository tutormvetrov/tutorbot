"""DB mixin for student progress, achievements, and lesson feedback."""
from __future__ import annotations

from datetime import datetime


class DatabaseProgressMixin:
    """Queries for progress card, achievements, and lesson feedback."""

    # ── Progress card data ──────────────────────────────────────────────────

    async def get_student_progress(self, student_id: int) -> dict:
        """Aggregate progress data for a single student."""
        row = await self.execute(
            """
            WITH monthly_lessons AS (
                SELECT COUNT(*) AS cnt
                FROM lessons
                WHERE student_id = $1
                  AND status IN ('active', 'completed')
                  AND lesson_date >= date_trunc('month', now())
            ),
            total_lessons AS (
                SELECT COUNT(*) AS cnt,
                       MIN(lesson_date) AS first_lesson_date,
                       MAX(lesson_date) AS last_lesson_date
                FROM lessons
                WHERE student_id = $1
                  AND status IN ('active', 'completed')
            ),
            monthly_hw AS (
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status = 'done') AS done
                FROM homework
                WHERE student_id = $1
                  AND created_at >= date_trunc('month', now())
            ),
            plan_progress AS (
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status = 'completed') AS done
                FROM study_plan_checklist_items ci
                WHERE ci.student_id = $1
                  AND EXISTS (
                      SELECT 1 FROM student_learning_plans sp
                      WHERE sp.student_id = $1 AND sp.status = 'active'
                  )
            ),
            achievements AS (
                SELECT COUNT(*) AS cnt
                FROM student_achievements
                WHERE user_id = $1
            )
            SELECT ml.cnt AS lessons_this_month,
                   tl.cnt AS total_lessons,
                   tl.first_lesson_date,
                   tl.last_lesson_date,
                   mh.total AS hw_total,
                   mh.done AS hw_done,
                   pp.total AS plan_total,
                   pp.done AS plan_done,
                   a.cnt AS achievement_count
            FROM monthly_lessons ml,
                 total_lessons tl,
                 monthly_hw mh,
                 plan_progress pp,
                 achievements a
            """,
            student_id,
            fetchrow=True,
        )
        return dict(row) if row else {}

    # ── Achievements CRUD ───────────────────────────────────────────────────

    async def get_student_achievements(self, user_id: int) -> list:
        """All achievements for a student, ordered by unlock date."""
        return await self.execute(
            """
            SELECT achievement_key, unlocked_at
            FROM student_achievements
            WHERE user_id = $1
            ORDER BY unlocked_at
            """,
            user_id,
            fetch=True,
        )

    async def grant_achievement(
        self,
        user_id: int,
        achievement_key: str,
        unlocked_at: datetime | None = None,
        notified: bool = False,
    ) -> bool:
        """Grant an achievement. Returns True if newly inserted, False if already existed."""
        result = await self.execute(
            """
            INSERT INTO student_achievements (user_id, achievement_key, unlocked_at, notified)
            VALUES ($1, $2, COALESCE($3, NOW()), $4)
            ON CONFLICT (user_id, achievement_key) DO NOTHING
            RETURNING id
            """,
            user_id,
            achievement_key,
            unlocked_at,
            notified,
            fetchval=True,
        )
        return result is not None

    async def get_unnotified_achievements(self) -> list:
        """All achievements that need congratulation messages."""
        return await self.execute(
            """
            SELECT sa.id, sa.user_id, sa.achievement_key, sa.unlocked_at,
                   u.full_name, u.speech_style
            FROM student_achievements sa
            JOIN users u ON u.telegram_id = sa.user_id
            WHERE sa.notified = false
              AND u.is_active = true
            ORDER BY sa.unlocked_at
            """,
            fetch=True,
        )

    async def mark_achievement_notified(self, achievement_id: int) -> None:
        await self.execute(
            "UPDATE student_achievements SET notified = true WHERE id = $1",
            achievement_id,
            execute=True,
        )

    async def count_all_possible_achievements(self) -> int:
        """Total number of defined achievements (hardcoded constant)."""
        return 12

    # ── Lesson feedback CRUD ────────────────────────────────────────────────

    async def save_lesson_feedback(
        self, lesson_id: int, user_id: int, rating: str,
    ) -> bool:
        """Save feedback. Returns True if newly inserted."""
        result = await self.execute(
            """
            INSERT INTO lesson_feedback (lesson_id, user_id, rating)
            VALUES ($1, $2, $3)
            ON CONFLICT (lesson_id, user_id) DO NOTHING
            RETURNING id
            """,
            lesson_id,
            user_id,
            rating,
            fetchval=True,
        )
        return result is not None

    async def get_recent_feedback(self, user_id: int, limit: int = 5) -> list:
        """Recent lesson feedback for a student."""
        return await self.execute(
            """
            SELECT lf.rating, lf.created_at, l.lesson_date
            FROM lesson_feedback lf
            JOIN lessons l ON l.id = lf.lesson_id
            WHERE lf.user_id = $1
            ORDER BY lf.created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
            fetch=True,
        )

    async def get_hard_feedback_today(self) -> list:
        """Students who rated a lesson 'hard' in the last 24 hours."""
        return await self.execute(
            """
            SELECT lf.user_id, u.full_name, l.lesson_date
            FROM lesson_feedback lf
            JOIN users u ON u.telegram_id = lf.user_id
            JOIN lessons l ON l.id = lf.lesson_id
            WHERE lf.rating = 'hard'
              AND lf.created_at >= now() - interval '24 hours'
            ORDER BY lf.created_at DESC
            """,
            fetch=True,
        )

    async def get_feedback_exists(self, lesson_id: int, user_id: int) -> bool:
        """Check if feedback already exists for this lesson+user."""
        result = await self.execute(
            "SELECT 1 FROM lesson_feedback WHERE lesson_id = $1 AND user_id = $2",
            lesson_id,
            user_id,
            fetchval=True,
        )
        return result is not None

    # ── Feedback request tracking ───────────────────────────────────────────

    async def get_lessons_for_feedback_request(self) -> list:
        """Lessons that ended 30min-4h ago, not yet asked for feedback."""
        return await self.execute(
            """
            SELECT l.id AS lesson_id, l.student_id, l.lesson_date,
                   u.full_name, u.speech_style
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.status IN ('active', 'completed')
              AND l.lesson_date < now() - interval '30 minutes'
              AND l.lesson_date > now() - interval '4 hours'
              AND COALESCE(l.feedback_request_sent, false) = false
              AND u.is_active = true
              AND u.role = 'student'
            ORDER BY l.lesson_date
            """,
            fetch=True,
        )

    async def mark_feedback_request_sent(self, lesson_id: int) -> None:
        await self.execute(
            "UPDATE lessons SET feedback_request_sent = true WHERE id = $1",
            lesson_id,
            execute=True,
        )

    # ── Achievement metrics helpers ─────────────────────────────────────────

    async def get_student_hw_perfect_months(self, student_id: int) -> list[str]:
        """Return list of YYYY-MM strings where all HW was done on time (>=3 HW, none overdue)."""
        return await self.execute(
            """
            SELECT to_char(created_at, 'YYYY-MM') AS month
            FROM homework
            WHERE student_id = $1
              AND status = 'done'
            GROUP BY to_char(created_at, 'YYYY-MM')
            HAVING COUNT(*) >= 3
               AND COUNT(*) FILTER (
                   WHERE deadline IS NOT NULL
                     AND created_at > deadline + interval '1 day'
               ) = 0
               AND COUNT(*) = (
                   SELECT COUNT(*)
                   FROM homework h2
                   WHERE h2.student_id = $1
                     AND to_char(h2.created_at, 'YYYY-MM') = to_char(homework.created_at, 'YYYY-MM')
               )
            """,
            student_id,
            fetch=True,
        )

    async def get_nth_lesson_date(self, student_id: int, n: int) -> datetime | None:
        """Date of the Nth lesson (1-indexed) for backfill."""
        return await self.execute(
            """
            SELECT lesson_date
            FROM lessons
            WHERE student_id = $1
              AND status IN ('active', 'completed')
            ORDER BY lesson_date
            LIMIT 1 OFFSET $2
            """,
            student_id,
            n - 1,
            fetchval=True,
        )
