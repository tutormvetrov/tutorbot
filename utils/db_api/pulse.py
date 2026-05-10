"""DB mixin for Teacher Pulse: nudges, touches, health dashboard queries."""
from __future__ import annotations

import json
from datetime import datetime


class DatabasePulseMixin:
    """All pulse-related database queries."""

    # ── Homework nudges ──────────────────────────────────────────────────────

    async def get_lessons_needing_nudge(self, since: datetime) -> list:
        """Lessons since `since` that have no HW created after lesson_date
        and no resolved/open nudge at stage 3."""
        return await self.execute(
            """
            SELECT l.id AS lesson_id,
                   l.student_id,
                   l.lesson_date,
                   u.full_name,
                   u.speech_style,
                   sg.id AS group_id,
                   sg.primary_student_id
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            LEFT JOIN student_groups sg
                   ON sg.primary_student_id = l.student_id
                  AND sg.is_active = true
            WHERE l.lesson_date >= $1
              AND l.lesson_date < now()
              AND l.status IN ('active', 'completed')
              AND u.is_active = true
              AND COALESCE(u.homework_exempt, false) = false
              AND (u.frozen_until IS NULL OR u.frozen_until < NOW())
              AND NOT EXISTS (
                  SELECT 1 FROM homework h
                  WHERE h.student_id = l.student_id
                    AND h.created_at > l.lesson_date
              )
              AND NOT EXISTS (
                  SELECT 1 FROM homework_nudges hn
                  WHERE hn.lesson_id = l.id
                    AND (hn.resolved_at IS NOT NULL OR hn.stage >= 3)
              )
            ORDER BY l.lesson_date
            """,
            since,
            fetch=True,
        )

    async def get_open_nudge_for_lesson(self, lesson_id: int) -> dict | None:
        """Get the latest open (unresolved) nudge for a specific lesson."""
        return await self.execute(
            """
            SELECT id, student_id, lesson_id, stage, sent_at, created_at
            FROM homework_nudges
            WHERE lesson_id = $1 AND resolved_at IS NULL
            ORDER BY stage DESC
            LIMIT 1
            """,
            lesson_id,
            fetchrow=True,
        )

    async def get_open_nudges_for_student(self, student_id: int) -> list:
        """All open nudges for a student (for auto-resolve on HW creation)."""
        return await self.execute(
            """
            SELECT id, lesson_id, stage, sent_at
            FROM homework_nudges
            WHERE student_id = $1 AND resolved_at IS NULL
            ORDER BY sent_at DESC
            """,
            student_id,
            fetch=True,
        )

    async def create_nudge(self, student_id: int, lesson_id: int, stage: int = 1) -> int:
        """Insert a new nudge row and return its id."""
        return await self.execute(
            """
            INSERT INTO homework_nudges (student_id, lesson_id, stage)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            student_id,
            lesson_id,
            stage,
            fetchval=True,
        )

    async def escalate_nudge(self, nudge_id: int, new_stage: int) -> None:
        """Bump an existing nudge to the next stage."""
        await self.execute(
            """
            UPDATE homework_nudges
            SET stage = $2, sent_at = now()
            WHERE id = $1
            """,
            nudge_id,
            new_stage,
            execute=True,
        )

    async def resolve_nudge(self, nudge_id: int, resolution: str) -> None:
        """Close a nudge chain."""
        await self.execute(
            """
            UPDATE homework_nudges
            SET resolved_at = now(), resolution = $2
            WHERE id = $1
            """,
            nudge_id,
            resolution,
            execute=True,
        )

    async def resolve_nudges_for_student(self, student_id: int, resolution: str) -> int:
        """Resolve all open nudges for a student. Returns count resolved."""
        result = await self.execute(
            """
            UPDATE homework_nudges
            SET resolved_at = now(), resolution = $2
            WHERE student_id = $1 AND resolved_at IS NULL
            RETURNING id
            """,
            student_id,
            resolution,
            fetch=True,
        )
        return len(result) if result else 0

    async def count_open_nudges(self, student_id: int) -> int:
        """Count unresolved nudges for a student."""
        result = await self.execute(
            "SELECT count(*) FROM homework_nudges WHERE student_id = $1 AND resolved_at IS NULL",
            student_id,
            fetchval=True,
        )
        return int(result) if result else 0

    # ── Student touches ──────────────────────────────────────────────────────

    async def log_touch(
        self,
        student_id: int,
        template_type: str,
        template_key: str | None,
        context_source: str,
        context_snippet: str | None,
        template_index: int | None = None,
    ) -> None:
        """Record a sent touch for dedup/rate-limiting."""
        await self.execute(
            """
            INSERT INTO student_touches
                (student_id, template_type, template_key, context_source,
                 context_snippet, template_index)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            student_id,
            template_type,
            template_key,
            context_source,
            context_snippet,
            template_index,
            execute=True,
        )

    async def get_recent_touches(self, student_id: int, since: datetime) -> list:
        """Touches sent to a student since a given datetime."""
        return await self.execute(
            """
            SELECT id, template_type, template_key, template_index, sent_at
            FROM student_touches
            WHERE student_id = $1 AND sent_at >= $2
            ORDER BY sent_at DESC
            """,
            student_id,
            since,
            fetch=True,
        )

    async def get_last_touches(self, limit: int = 20) -> list:
        """Latest touches across all students for the admin audit panel."""
        return await self.execute(
            """
            SELECT t.id,
                   t.student_id,
                   u.full_name,
                   u.preferred_name,
                   t.template_type,
                   t.template_index,
                   t.context_source,
                   t.context_snippet,
                   t.sent_at
            FROM student_touches t
            LEFT JOIN users u ON u.telegram_id = t.student_id
            ORDER BY t.sent_at DESC
            LIMIT $1
            """,
            limit,
            fetch=True,
        )

    # ── Pulse health data ────────────────────────────────────────────────────

    async def get_all_pulse_data(self) -> list:
        """Bulk query: per-student health data for all active students.

        Returns rows with: telegram_id, full_name, speech_style, is_pair,
        pair_title, last_lesson_date, last_hw_created_at, balance,
        open_nudge_count, first_lesson_date, touches_enabled, goal_text.
        """
        return await self.execute(
            """
            WITH student_base AS (
                SELECT u.telegram_id,
                       u.full_name,
                       u.speech_style,
                       u.touches_enabled,
                       COALESCE(u.homework_exempt, false) AS homework_exempt,
                       u.goal_text,
                       sg.id AS group_id,
                       sg.title AS pair_title,
                       sg.primary_student_id,
                       CASE WHEN sg.id IS NOT NULL THEN true ELSE false END AS is_pair
                FROM users u
                LEFT JOIN student_groups sg
                       ON sg.primary_student_id = u.telegram_id
                      AND sg.is_active = true
                WHERE u.role = 'student'
                  AND u.is_active = true
            ),
            last_lesson AS (
                SELECT student_id,
                       MAX(lesson_date) AS last_lesson_date,
                       MIN(lesson_date) AS first_lesson_date,
                       COUNT(*) FILTER (WHERE status IN ('active', 'completed')) AS total_lessons
                FROM lessons
                GROUP BY student_id
            ),
            last_hw AS (
                SELECT student_id,
                       MAX(created_at) AS last_hw_created_at
                FROM homework
                GROUP BY student_id
            ),
            balances AS (
                SELECT student_id,
                       COALESCE(SUM(amount_lessons), 0) AS balance
                FROM balance_transactions
                GROUP BY student_id
            ),
            open_nudges AS (
                SELECT student_id,
                       COUNT(*) AS open_nudge_count
                FROM homework_nudges
                WHERE resolved_at IS NULL
                GROUP BY student_id
            )
            SELECT sb.telegram_id,
                   sb.full_name,
                   sb.speech_style,
                   sb.touches_enabled,
                   sb.homework_exempt,
                   sb.goal_text,
                   sb.is_pair,
                   sb.pair_title,
                   sb.primary_student_id,
                   ll.last_lesson_date,
                   ll.first_lesson_date,
                   ll.total_lessons,
                   lh.last_hw_created_at,
                   COALESCE(b.balance, 0) AS balance,
                   COALESCE(on2.open_nudge_count, 0) AS open_nudge_count
            FROM student_base sb
            LEFT JOIN last_lesson ll ON ll.student_id = sb.telegram_id
            LEFT JOIN last_hw lh ON lh.student_id = sb.telegram_id
            LEFT JOIN balances b ON b.student_id = sb.telegram_id
            LEFT JOIN open_nudges on2 ON on2.student_id = sb.telegram_id
            ORDER BY sb.full_name
            """,
            fetch=True,
        )

    async def get_today_lessons_for_briefing(
        self,
        today_start: datetime,
        tomorrow_start: datetime,
    ) -> list:
        """Today's lessons with student names, for the morning briefing."""
        return await self.execute(
            """
            SELECT l.lesson_date,
                   l.student_id,
                   u.full_name,
                   sg.title AS pair_title,
                   CASE WHEN sg.id IS NOT NULL THEN true ELSE false END AS is_pair
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            LEFT JOIN student_groups sg
                   ON sg.primary_student_id = l.student_id
                  AND sg.is_active = true
            WHERE l.lesson_date >= $1
              AND l.lesson_date < $2
              AND l.status IN ('active', 'completed')
            ORDER BY l.lesson_date
            """,
            today_start,
            tomorrow_start,
            fetch=True,
        )

    async def get_touch_candidates(self) -> list:
        """Active students eligible for between-lesson touches.

        Returns: telegram_id, full_name, speech_style, goal_text,
        last_lesson_date, next_lesson_date, teacher_comment, has_active_hw,
        is_pair, pair_title, partner_name, touches_enabled.
        """
        return await self.execute(
            """
            WITH student_base AS (
                SELECT u.telegram_id,
                       u.full_name,
                       u.preferred_name,
                       u.speech_style,
                       u.goal_text,
                       u.touches_enabled,
                       COALESCE(u.homework_exempt, false) AS homework_exempt,
                       sg.id AS group_id,
                       sg.title AS pair_title,
                       CASE WHEN sg.id IS NOT NULL THEN true ELSE false END AS is_pair
                FROM users u
                LEFT JOIN student_groups sg
                       ON sg.primary_student_id = u.telegram_id
                      AND sg.is_active = true
                WHERE u.role = 'student'
                  AND u.is_active = true
                  AND u.touches_enabled = true
                  AND (u.frozen_until IS NULL OR u.frozen_until < NOW())
            ),
            last_lesson_info AS (
                SELECT l.student_id,
                       l.lesson_date AS last_lesson_date,
                       l.teacher_comment
                FROM lessons l
                WHERE l.lesson_date = (
                    SELECT MAX(l2.lesson_date)
                    FROM lessons l2
                    WHERE l2.student_id = l.student_id
                      AND l2.lesson_date < now()
                      AND l2.status IN ('active', 'completed')
                )
            ),
            next_lesson_info AS (
                SELECT student_id,
                       MIN(lesson_date) AS next_lesson_date
                FROM lessons
                WHERE lesson_date > now()
                  AND status = 'active'
                GROUP BY student_id
            ),
            active_hw AS (
                SELECT student_id,
                       true AS has_active_hw
                FROM homework
                WHERE status = 'active'
                GROUP BY student_id
            ),
            partner_info AS (
                SELECT sgm.group_id,
                       sgm.member_name AS partner_name
                FROM student_group_members sgm
                WHERE sgm.member_role = 'partner'
            )
            SELECT sb.telegram_id,
                   sb.full_name,
                   sb.preferred_name,
                   sb.speech_style,
                   sb.goal_text,
                   sb.is_pair,
                   sb.pair_title,
                   sb.homework_exempt,
                   lli.last_lesson_date,
                   lli.teacher_comment,
                   nli.next_lesson_date,
                   COALESCE(ah.has_active_hw, false) AS has_active_hw,
                   pi.partner_name
            FROM student_base sb
            LEFT JOIN last_lesson_info lli ON lli.student_id = sb.telegram_id
            LEFT JOIN next_lesson_info nli ON nli.student_id = sb.telegram_id
            LEFT JOIN active_hw ah ON ah.student_id = sb.telegram_id
            LEFT JOIN partner_info pi ON pi.group_id = sb.group_id
            """,
            fetch=True,
        )

    async def get_last_teacher_comment(self, student_id: int) -> str | None:
        """Get teacher_comment from the most recent completed lesson."""
        return await self.execute(
            """
            SELECT teacher_comment
            FROM lessons
            WHERE student_id = $1
              AND lesson_date < now()
              AND status IN ('active', 'completed')
              AND teacher_comment IS NOT NULL
              AND teacher_comment != ''
            ORDER BY lesson_date DESC
            LIMIT 1
            """,
            student_id,
            fetchval=True,
        )
