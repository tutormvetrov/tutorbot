from data.config import normalize_person_name
from utils.text_utils import extract_student_name


class DatabaseUserMixin:
    async def get_user(self, telegram_id: int):
        return await self.execute(
            """
            SELECT
                u.*,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.lesson_date IS NOT NULL
                ) AS first_lesson_date
            FROM users u
            WHERE u.telegram_id = $1
            """,
            telegram_id, fetchrow=True,
        )

    async def get_telegram_block(self, telegram_id: int):
        return await self.execute(
            """
            SELECT
                b.telegram_id,
                b.reason,
                b.blocked_by,
                b.blocked_at,
                b.previous_is_active,
                u.full_name,
                u.username,
                u.role,
                u.is_active
            FROM blocked_telegram_ids b
            LEFT JOIN users u
              ON u.telegram_id = b.telegram_id
            WHERE b.telegram_id = $1
            """,
            telegram_id,
            fetchrow=True,
        )

    async def is_telegram_id_blocked(self, telegram_id: int) -> bool:
        return bool(
            await self.execute(
                "SELECT 1 FROM blocked_telegram_ids WHERE telegram_id = $1",
                telegram_id,
                fetchval=True,
            )
        )

    async def get_blocked_telegram_ids(self, limit: int = 20):
        return await self.execute(
            """
            SELECT
                b.telegram_id,
                b.reason,
                b.blocked_by,
                b.blocked_at,
                b.previous_is_active,
                u.full_name,
                u.username,
                u.role,
                u.is_active
            FROM blocked_telegram_ids b
            LEFT JOIN users u
              ON u.telegram_id = b.telegram_id
            ORDER BY b.blocked_at DESC, b.telegram_id DESC
            LIMIT $1
            """,
            limit,
            fetch=True,
        )

    async def block_telegram_id(
        self,
        telegram_id: int,
        blocked_by: int | None = None,
        reason: str | None = None,
    ):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing_user = await conn.fetchrow(
                    """
                    SELECT telegram_id, is_active
                    FROM users
                    WHERE telegram_id = $1
                    """,
                    telegram_id,
                )
                previous_is_active = None
                if existing_user is not None:
                    previous_is_active = existing_user["is_active"]

                await conn.execute(
                    """
                    INSERT INTO blocked_telegram_ids (
                        telegram_id,
                        reason,
                        blocked_by,
                        previous_is_active
                    )
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET reason = EXCLUDED.reason,
                        blocked_by = EXCLUDED.blocked_by,
                        blocked_at = CURRENT_TIMESTAMP,
                        previous_is_active = COALESCE(
                            blocked_telegram_ids.previous_is_active,
                            EXCLUDED.previous_is_active
                        )
                    """,
                    telegram_id,
                    reason,
                    blocked_by,
                    previous_is_active,
                )

                if existing_user is not None:
                    await conn.execute(
                        "UPDATE users SET is_active = false WHERE telegram_id = $1",
                        telegram_id,
                    )

        return await self.get_telegram_block(telegram_id)

    async def unblock_telegram_id(self, telegram_id: int) -> dict:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                block_row = await conn.fetchrow(
                    """
                    SELECT previous_is_active
                    FROM blocked_telegram_ids
                    WHERE telegram_id = $1
                    """,
                    telegram_id,
                )
                if block_row is None:
                    return {"removed": False, "reactivated": False}

                await conn.execute(
                    "DELETE FROM blocked_telegram_ids WHERE telegram_id = $1",
                    telegram_id,
                )

                reactivated = False
                if block_row["previous_is_active"] is True:
                    result = await conn.execute(
                        """
                        UPDATE users
                        SET is_active = true
                        WHERE telegram_id = $1
                          AND role IN ('student', 'parent')
                        """,
                        telegram_id,
                    )
                    reactivated = not result.endswith("0")

        return {"removed": True, "reactivated": reactivated}

    async def get_all_students(self):
        return await self.execute(
            """
            SELECT *
            FROM users
            WHERE role = 'student'
              AND is_active = true
              AND COALESCE(is_internal_account, false) = false
            ORDER BY full_name
            """,
            fetch=True,
        )

    async def find_active_student_by_name(self, full_name: str):
        normalized_target = normalize_person_name(full_name)
        if not normalized_target:
            return None
        students = await self.get_all_students()
        for student in students:
            if normalize_person_name(student.get("full_name") or "") == normalized_target:
                return student
        return None

    async def upsert_parent_student_link(self, parent_id: int, student_info: str, student_id: int | None = None):
        normalized_target = normalize_person_name(extract_student_name(student_info))
        links = await self.execute(
            """
            SELECT id, student_info, student_id
            FROM student_parent
            WHERE parent_id = $1
              AND is_active = true
            ORDER BY id
            """,
            parent_id,
            fetch=True,
        )
        for link in links:
            normalized_existing = normalize_person_name(extract_student_name(link.get("student_info") or ""))
            if normalized_existing == normalized_target:
                await self.execute(
                    """
                    UPDATE student_parent
                    SET student_info = $2,
                        student_id = $3,
                        is_active = true
                    WHERE id = $1
                    """,
                    link["id"],
                    student_info,
                    student_id,
                    execute=True,
                )
                return link["id"]

        return await self.execute(
            """
            INSERT INTO student_parent (parent_id, student_id, student_info)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            parent_id,
            student_id,
            student_info,
            fetchval=True,
        )

    async def sync_parent_links_for_student(self, student_id: int, full_name: str):
        normalized_student_name = normalize_person_name(full_name)
        if not normalized_student_name:
            return 0
        links = await self.execute(
            """
            SELECT id, student_info, student_id
            FROM student_parent
            WHERE is_active = true
            """,
            fetch=True,
        )
        updated = 0
        for link in links:
            normalized_link_name = normalize_person_name(extract_student_name(link.get("student_info") or ""))
            if normalized_link_name != normalized_student_name:
                continue
            if link.get("student_id") == student_id:
                continue
            await self.execute(
                "UPDATE student_parent SET student_id = $2 WHERE id = $1",
                link["id"],
                student_id,
                execute=True,
            )
            updated += 1
        return updated

    async def sync_all_parent_links(self):
        students = await self.get_all_students()
        updated = 0
        for student in students:
            updated += await self.sync_parent_links_for_student(
                student["telegram_id"],
                student["full_name"],
            )
        return updated

    async def get_parent_children(self, parent_id: int) -> list[str]:
        links = await self.execute(
            """
            SELECT sp.student_info, sp.student_id, u.full_name
            FROM student_parent sp
            LEFT JOIN users u
              ON u.telegram_id = sp.student_id
            WHERE sp.parent_id = $1
              AND sp.is_active = true
            ORDER BY sp.id
            """,
            parent_id,
            fetch=True,
        )
        items = []
        seen = set()
        for link in links:
            label = link.get("full_name") or link.get("student_info") or ""
            dedupe_key = normalize_person_name(extract_student_name(label))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            if label:
                items.append(label)
        return items

    async def get_parent_children_overview(self, parent_id: int):
        return await self.execute(
            """
            SELECT
                sp.id AS link_id,
                sp.parent_id,
                sp.student_id,
                sp.student_info,
                COALESCE(u.full_name, sp.student_info) AS child_label,
                CASE
                    WHEN sp.student_id IS NULL THEN 'waiting_link'
                    WHEN u.telegram_id IS NOT NULL AND u.role = 'student' AND u.is_active = true THEN 'linked'
                    ELSE 'inactive_student'
                END AS link_status,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = sp.student_id
                      AND l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                ) AS next_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = sp.student_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = sp.student_id
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance,
                COALESCE(u.lesson_format, 'online') AS lesson_format
            FROM student_parent sp
            LEFT JOIN users u
              ON u.telegram_id = sp.student_id
            WHERE sp.parent_id = $1
              AND sp.is_active = true
            ORDER BY sp.id
            """,
            parent_id,
            fetch=True,
        )

    async def get_parent_child_link(self, parent_id: int, link_id: int):
        return await self.execute(
            """
            SELECT
                sp.id AS link_id,
                sp.parent_id,
                sp.student_id,
                sp.student_info,
                COALESCE(u.full_name, sp.student_info) AS child_label,
                CASE
                    WHEN sp.student_id IS NULL THEN 'waiting_link'
                    WHEN u.telegram_id IS NOT NULL AND u.role = 'student' AND u.is_active = true THEN 'linked'
                    ELSE 'inactive_student'
                END AS link_status,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = sp.student_id
                      AND l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                ) AS next_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = sp.student_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = sp.student_id
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance,
                COALESCE(u.lesson_format, 'online') AS lesson_format
            FROM student_parent sp
            LEFT JOIN users u
              ON u.telegram_id = sp.student_id
            WHERE sp.parent_id = $1
              AND sp.id = $2
              AND sp.is_active = true
            """,
            parent_id,
            link_id,
            fetchrow=True,
        )

    async def get_parent_child_schedule(self, parent_id: int, link_id: int):
        return await self.execute(
            """
            SELECT l.*
            FROM lessons l
            JOIN student_parent sp
              ON sp.student_id = l.student_id
             AND sp.parent_id = $1
             AND sp.id = $2
             AND sp.is_active = true
            WHERE l.status = 'active'
            ORDER BY l.lesson_date ASC NULLS LAST, l.created_at DESC
            """,
            parent_id,
            link_id,
            fetch=True,
        )

    async def get_parent_child_homework(self, parent_id: int, link_id: int, status: str = "active"):
        return await self.execute(
            """
            SELECT h.*
            FROM homework h
            JOIN student_parent sp
              ON sp.student_id = h.student_id
             AND sp.parent_id = $1
             AND sp.id = $2
             AND sp.is_active = true
            WHERE h.status = $3
            ORDER BY h.deadline ASC NULLS LAST, h.created_at DESC
            """,
            parent_id,
            link_id,
            status,
            fetch=True,
        )

    async def get_parent_child_payments(self, parent_id: int, link_id: int, limit: int = 5):
        return await self.execute(
            """
            SELECT p.*
            FROM payments p
            JOIN student_parent sp
              ON sp.student_id = p.student_id
             AND sp.parent_id = $1
             AND sp.id = $2
             AND sp.is_active = true
            ORDER BY p.created_at DESC
            LIMIT $3
            """,
            parent_id,
            link_id,
            limit,
            fetch=True,
        )

    async def get_students_overview(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                u.language,
                u.level,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = u.telegram_id
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.lesson_date IS NOT NULL
                ) AS first_lesson_date,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = u.telegram_id
                      AND l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                ) AS next_lesson_date,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                COALESCE(u.speech_style, 'formal') AS speech_style
            FROM users u
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            ORDER BY u.full_name
            """,
            fetch=True,
        )

    async def get_parents_overview(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                u.username,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM student_parent sp
                    WHERE sp.parent_id = u.telegram_id
                      AND sp.is_active = true
                ), 0) AS children_count,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM student_parent sp
                    WHERE sp.parent_id = u.telegram_id
                      AND sp.is_active = true
                      AND sp.student_id IS NOT NULL
                ), 0) AS linked_children_count
            FROM users u
            WHERE u.role = 'parent'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            ORDER BY u.full_name
            """,
            fetch=True,
        )

    async def deactivate_parent(self, telegram_id: int):
        await self.execute(
            """
            UPDATE users
            SET is_active = false
            WHERE telegram_id = $1
              AND role = 'parent'
            """,
            telegram_id,
            execute=True,
        )

    async def get_parent_deletion_snapshot(self, telegram_id: int) -> dict:
        user = await self.get_user(telegram_id)
        if not user or user.get("role") != "parent":
            return {}

        children_count = await self.execute(
            """
            SELECT COUNT(*)::int
            FROM student_parent
            WHERE parent_id = $1
              AND is_active = true
            """,
            telegram_id,
            fetchval=True,
        ) or 0
        linked_children_count = await self.execute(
            """
            SELECT COUNT(*)::int
            FROM student_parent
            WHERE parent_id = $1
              AND is_active = true
              AND student_id IS NOT NULL
            """,
            telegram_id,
            fetchval=True,
        ) or 0
        payments_as_payer = await self.execute(
            """
            SELECT COUNT(*)::int
            FROM payments
            WHERE payer_id = $1
            """,
            telegram_id,
            fetchval=True,
        ) or 0

        return {
            "children_count": children_count,
            "linked_children_count": linked_children_count,
            "payments_as_payer": payments_as_payer,
        }

    async def get_students_with_calendar_alias_counts(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(COUNT(csl.id), 0)::int AS alias_count
            FROM users u
            LEFT JOIN calendar_student_links csl
              ON csl.student_id = u.telegram_id
             AND csl.is_active = true
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            GROUP BY u.telegram_id, u.full_name
            ORDER BY u.full_name
            """,
            fetch=True,
        )

    async def deactivate_student(self, telegram_id: int):
        await self.execute(
            "UPDATE users SET is_active = false WHERE telegram_id = $1",
            telegram_id, execute=True,
        )

    async def delete_student(self, telegram_id: int):
        await self.delete_user_fully(telegram_id)

    async def get_user_deletion_snapshot(self, telegram_id: int) -> dict:
        user = await self.get_user(telegram_id)
        if not user:
            return {}

        return {
            "role": user["role"],
            "homework": await self.execute(
                "SELECT COUNT(*) FROM homework WHERE student_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
            "lessons": await self.execute(
                "SELECT COUNT(*) FROM lessons WHERE student_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
            "payments_as_student": await self.execute(
                "SELECT COUNT(*) FROM payments WHERE student_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
            "payments_as_payer": await self.execute(
                "SELECT COUNT(*) FROM payments WHERE payer_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
            "calendar_links": await self.execute(
                "SELECT COUNT(*) FROM calendar_student_links WHERE student_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
            "parent_links_as_student": await self.execute(
                "SELECT COUNT(*) FROM student_parent WHERE student_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
            "parent_links_as_parent": await self.execute(
                "SELECT COUNT(*) FROM student_parent WHERE parent_id = $1",
                telegram_id, fetchval=True,
            ) or 0,
        }

    async def delete_user_fully(self, telegram_id: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM calendar_student_links WHERE student_id = $1", telegram_id)
                await conn.execute("DELETE FROM homework WHERE student_id = $1", telegram_id)
                await conn.execute("DELETE FROM lessons WHERE student_id = $1", telegram_id)
                await conn.execute(
                    "DELETE FROM payments WHERE student_id = $1 OR payer_id = $1", telegram_id
                )
                await conn.execute(
                    "DELETE FROM student_parent WHERE parent_id = $1", telegram_id
                )
                await conn.execute(
                    "DELETE FROM student_parent WHERE student_id = $1", telegram_id
                )
                await conn.execute(
                    "DELETE FROM users WHERE telegram_id = $1", telegram_id
                )

    async def delete_parent_preserving_history(self, telegram_id: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE payments SET payer_id = NULL WHERE payer_id = $1",
                    telegram_id,
                )
                await conn.execute(
                    "DELETE FROM student_parent WHERE parent_id = $1",
                    telegram_id,
                )
                await conn.execute(
                    "DELETE FROM users WHERE telegram_id = $1 AND role = 'parent'",
                    telegram_id,
                )

    async def get_students_for_review(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style,
                MIN(l.lesson_date) AS first_lesson
            FROM users u
            JOIN lessons l ON l.student_id = u.telegram_id
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
              AND u.review_sent = false
              AND l.lesson_date IS NOT NULL
            GROUP BY u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal')
            HAVING MIN(l.lesson_date) <= NOW() - INTERVAL '21 days'
            """,
            fetch=True,
        )

    async def mark_review_sent(self, telegram_id: int):
        await self.execute(
            "UPDATE users SET review_sent = true WHERE telegram_id = $1",
            telegram_id, execute=True,
        )

    async def get_students_with_balances(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style,
                COALESCE(SUM(p.lessons_remaining), 0)::int AS lesson_balance
            FROM users u
            LEFT JOIN payments p
              ON p.student_id = u.telegram_id
             AND p.status = 'confirmed'
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            GROUP BY u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal')
            ORDER BY u.full_name
            """,
            fetch=True,
        )

    async def set_speech_style(self, telegram_id: int, value: str):
        await self.execute(
            "UPDATE users SET speech_style = $1 WHERE telegram_id = $2",
            value,
            telegram_id,
            execute=True,
        )

    async def set_lesson_duration(self, telegram_id: int, minutes: int):
        await self.execute(
            "UPDATE users SET lesson_duration_minutes = $1 WHERE telegram_id = $2",
            minutes,
            telegram_id,
            execute=True,
        )

    async def save_student_bookmark(
        self,
        telegram_id: int,
        lesson_id: int,
        bookmark_text: str | None,
        bookmark_state: str,
    ):
        await self.execute(
            """
            UPDATE users
            SET current_bookmark_text = $1,
                current_bookmark_state = $2,
                current_bookmark_updated_at = CURRENT_TIMESTAMP,
                current_bookmark_lesson_id = $3
            WHERE telegram_id = $4
            """,
            bookmark_text,
            bookmark_state,
            lesson_id,
            telegram_id,
            execute=True,
        )

    async def get_admin_dashboard_snapshot(self):
        return await self.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)::int
                    FROM users u
                    WHERE u.role = 'student'
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS active_students,
                (
                    SELECT COUNT(*)::int
                    FROM lessons l
                    JOIN users u ON u.telegram_id = l.student_id
                    WHERE l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                      AND l.lesson_date::date = CURRENT_DATE
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS lessons_today,
                (
                    SELECT COUNT(*)::int
                    FROM (
                        SELECT u.telegram_id
                        FROM users u
                        LEFT JOIN payments p
                          ON p.student_id = u.telegram_id
                         AND p.status = 'confirmed'
                        WHERE u.role = 'student'
                          AND u.is_active = true
                          AND COALESCE(u.is_internal_account, false) = false
                        GROUP BY u.telegram_id
                        HAVING COALESCE(SUM(p.lessons_remaining), 0) = 0
                    ) unpaid
                ) AS unpaid_students,
                (
                    SELECT COUNT(*)::int
                    FROM lessons l
                    JOIN users u ON u.telegram_id = l.student_id
                    WHERE l.status = 'freeze_pending'
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS pending_freezes,
                (
                    SELECT COUNT(*)::int
                    FROM homework h
                    JOIN users u ON u.telegram_id = h.student_id
                    WHERE h.status = 'active'
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                ) AS active_homework,
                (
                    SELECT COUNT(*)::int
                    FROM users u
                    WHERE u.role = 'student'
                      AND u.is_active = true
                      AND COALESCE(u.is_internal_account, false) = false
                      AND NOT EXISTS (
                          SELECT 1
                          FROM lessons l
                          WHERE l.student_id = u.telegram_id
                            AND l.status = 'active'
                            AND l.lesson_date IS NOT NULL
                            AND l.lesson_date >= NOW()
                      )
                ) AS students_without_upcoming_lessons
            """,
            fetchrow=True,
        )

    async def get_parent_weekly_digest_rows(self, period_start, period_end):
        return await self.execute(
            """
            SELECT
                parent.telegram_id AS parent_id,
                parent.full_name AS parent_name,
                student.telegram_id AS student_id,
                student.full_name AS student_name,
                EXISTS (
                    SELECT 1
                    FROM lessons l
                    WHERE l.student_id = student.telegram_id
                      AND l.lesson_date >= $1
                      AND l.lesson_date < $2
                      AND l.status IN ('active', 'completed', 'freeze_pending', 'frozen')
                ) AS had_lesson,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = student.telegram_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = student.telegram_id
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance
                ,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = student.telegram_id
                      AND l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                ) AS next_lesson_date
            FROM student_parent sp
            JOIN users parent
              ON parent.telegram_id = sp.parent_id
             AND parent.role = 'parent'
             AND parent.is_active = true
            JOIN users student
              ON student.telegram_id = sp.student_id
             AND student.role = 'student'
             AND student.is_active = true
            WHERE sp.is_active = true
            ORDER BY parent.full_name, student.full_name
            """,
            period_start,
            period_end,
            fetch=True,
        )
