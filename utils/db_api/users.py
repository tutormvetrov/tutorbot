import secrets

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

    async def set_student_stage_override(self, telegram_id: int, stage: str | None):
        await self.execute(
            "UPDATE users SET student_stage_override = $2 WHERE telegram_id = $1",
            telegram_id, stage, execute=True,
        )

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

    async def get_active_parent_for_student(self, student_id: int):
        """Return the first active parent for a student, or None."""
        return await self.execute(
            """SELECT u.telegram_id, u.full_name, u.speech_style
            FROM student_parent sp
            JOIN users u ON u.telegram_id = sp.parent_id
                AND u.role = 'parent' AND u.is_active = true
            WHERE sp.student_id = $1 AND sp.is_active = true
            LIMIT 1""",
            student_id,
            fetchrow=True,
        )

    async def update_tariff_text(self, telegram_id: int, tariff_text: str | None):
        await self.execute(
            "UPDATE users SET tariff_text = $1 WHERE telegram_id = $2",
            tariff_text, telegram_id,
            execute=True,
        )

    async def create_student_pair(
        self,
        primary_student_id: int,
        primary_member_name: str,
        partner_name: str,
        *,
        title: str | None = None,
        onboarding_source: str = "admin",
    ) -> int:
        clean_primary = " ".join((primary_member_name or "").split()).strip()
        clean_partner = " ".join((partner_name or "").split()).strip()
        if not clean_primary or not clean_partner:
            raise ValueError("Both pair members must have names.")

        pair_title = title or f"{clean_primary} + {clean_partner}"
        group_id = await self.execute(
            """
            INSERT INTO student_groups (
                group_type,
                title,
                primary_student_id,
                balance_mode,
                homework_mode,
                onboarding_source
            )
            VALUES ('pair', $1, $2, 'shared', 'shared', $3)
            RETURNING id
            """,
            pair_title,
            primary_student_id,
            onboarding_source,
            fetchval=True,
        )
        await self.execute(
            """
            INSERT INTO student_group_members (
                group_id,
                student_id,
                member_name,
                member_role,
                has_bot_access
            )
            VALUES
                ($1, $2, $3, 'primary', true),
                ($1, NULL, $4, 'partner', false)
            """,
            group_id,
            primary_student_id,
            clean_primary,
            clean_partner,
            execute=True,
        )
        return int(group_id)

    def _pair_select_sql(self, where_clause: str) -> str:
        return f"""
            SELECT
                g.*,
                u.full_name AS primary_student_name,
                COALESCE((
                    SELECT SUM(p.lessons_remaining)::int
                    FROM payments p
                    WHERE p.student_id = g.primary_student_id
                      AND p.status = 'confirmed'
                ), 0) AS lesson_balance,
                (
                    SELECT MIN(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = g.primary_student_id
                      AND l.status = 'active'
                      AND l.lesson_date IS NOT NULL
                ) AS next_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = g.primary_student_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                ARRAY_REMOVE(ARRAY_AGG(
                    m.member_name
                    ORDER BY
                        CASE WHEN m.member_role = 'primary' THEN 0 ELSE 1 END,
                        m.id
                ), NULL) AS member_names,
                STRING_AGG(
                    CASE WHEN m.member_role <> 'primary' THEN m.member_name ELSE NULL END,
                    ', '
                    ORDER BY m.id
                ) AS partner_names
            FROM student_groups g
            JOIN users u
              ON u.telegram_id = g.primary_student_id
            LEFT JOIN student_group_members m
              ON m.group_id = g.id
            WHERE g.group_type = 'pair'
              AND g.is_active = true
              AND {where_clause}
            GROUP BY g.id, u.full_name
        """

    async def get_student_pair_for_student(self, student_id: int):
        return await self.execute(
            self._pair_select_sql(
                """
                (
                    g.primary_student_id = $1
                    OR EXISTS (
                        SELECT 1
                        FROM student_group_members sm
                        WHERE sm.group_id = g.id
                          AND sm.student_id = $1
                    )
                )
                """
            )
            + "\nORDER BY g.created_at DESC, g.id DESC LIMIT 1",
            student_id,
            fetchrow=True,
        )

    async def get_student_pair(self, group_id: int):
        return await self.execute(
            self._pair_select_sql("g.id = $1"),
            group_id,
            fetchrow=True,
        )

    async def get_student_pairs_overview(self):
        return await self.execute(
            self._pair_select_sql("true") + "\nORDER BY g.created_at DESC, g.id DESC",
            fetch=True,
        )

    async def ensure_student_pair_invite(self, group_id: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                member = await conn.fetchrow(
                    """
                    SELECT
                        m.id AS member_id,
                        m.group_id,
                        m.student_id,
                        m.member_name,
                        m.invite_token,
                        m.invite_created_at,
                        m.invite_used_at,
                        g.title,
                        g.primary_student_id,
                        u.full_name AS primary_student_name
                    FROM student_group_members m
                    JOIN student_groups g
                      ON g.id = m.group_id
                    JOIN users u
                      ON u.telegram_id = g.primary_student_id
                    WHERE m.group_id = $1
                      AND g.group_type = 'pair'
                      AND g.is_active = true
                      AND m.member_role <> 'primary'
                    ORDER BY
                        CASE WHEN m.student_id IS NULL THEN 0 ELSE 1 END,
                        m.id
                    LIMIT 1
                    """,
                    group_id,
                )
                if not member:
                    return None
                if member["invite_token"]:
                    return member

                token = secrets.token_urlsafe(18)
                return await conn.fetchrow(
                    """
                    UPDATE student_group_members m
                    SET invite_token = $2,
                        invite_created_at = CURRENT_TIMESTAMP
                    FROM student_groups g
                    JOIN users u
                      ON u.telegram_id = g.primary_student_id
                    WHERE m.id = $1
                      AND g.id = m.group_id
                    RETURNING
                        m.id AS member_id,
                        m.group_id,
                        m.student_id,
                        m.member_name,
                        m.invite_token,
                        m.invite_created_at,
                        m.invite_used_at,
                        g.title,
                        g.primary_student_id,
                        u.full_name AS primary_student_name
                    """,
                    member["member_id"],
                    token,
                )

    async def get_student_pair_invite(self, token: str):
        return await self.execute(
            """
            SELECT
                m.id AS member_id,
                m.group_id,
                m.student_id,
                m.member_name,
                m.invite_token,
                m.invite_created_at,
                m.invite_used_at,
                g.title,
                g.primary_student_id,
                u.full_name AS primary_student_name
            FROM student_group_members m
            JOIN student_groups g
              ON g.id = m.group_id
            JOIN users u
              ON u.telegram_id = g.primary_student_id
            WHERE m.invite_token = $1
              AND g.group_type = 'pair'
              AND g.is_active = true
            """,
            token,
            fetchrow=True,
        )

    async def accept_student_pair_invite(
        self,
        token: str,
        telegram_id: int,
        telegram_full_name: str,
        username: str | None = None,
    ):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                invite = await conn.fetchrow(
                    """
                    SELECT
                        m.id AS member_id,
                        m.group_id,
                        m.student_id,
                        m.member_name,
                        m.invite_token,
                        m.invite_created_at,
                        m.invite_used_at,
                        g.title,
                        g.primary_student_id,
                        u.full_name AS primary_student_name
                    FROM student_group_members m
                    JOIN student_groups g
                      ON g.id = m.group_id
                    JOIN users u
                      ON u.telegram_id = g.primary_student_id
                    WHERE m.invite_token = $1
                      AND g.group_type = 'pair'
                      AND g.is_active = true
                    FOR UPDATE OF m
                    """,
                    token,
                )
                if not invite:
                    return None
                if invite["student_id"] and invite["student_id"] != telegram_id:
                    return invite

                clean_name = " ".join((invite["member_name"] or telegram_full_name or "").split()).strip()
                if not clean_name:
                    clean_name = telegram_full_name or str(telegram_id)

                await conn.execute(
                    """
                    INSERT INTO users (telegram_id, full_name, username, role)
                    VALUES ($1, $2, $3, 'student')
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET full_name = EXCLUDED.full_name,
                        username = EXCLUDED.username,
                        role = EXCLUDED.role,
                        is_active = true
                    """,
                    telegram_id,
                    clean_name,
                    username,
                )
                await conn.execute(
                    """
                    UPDATE student_group_members
                    SET student_id = $2,
                        has_bot_access = true,
                        invite_used_at = COALESCE(invite_used_at, CURRENT_TIMESTAMP)
                    WHERE id = $1
                    """,
                    invite["member_id"],
                    telegram_id,
                )

        return await self.get_student_pair_for_student(telegram_id)

    async def deactivate_student_pair(self, group_id: int):
        await self.execute(
            "UPDATE student_groups SET is_active = false WHERE id = $1",
            group_id,
            execute=True,
        )

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
                (
                    SELECT MAX(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = sp.student_id
                      AND l.lesson_date IS NOT NULL
                      AND l.lesson_date < now()
                ) AS last_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = sp.student_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = sp.student_id
                      AND h.status = 'active'
                      AND h.deadline IS NOT NULL
                      AND h.deadline < now()
                ), 0) AS overdue_homework_count,
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
                (
                    SELECT MAX(l.lesson_date)
                    FROM lessons l
                    WHERE l.student_id = sp.student_id
                      AND l.lesson_date IS NOT NULL
                      AND l.lesson_date < now()
                ) AS last_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = sp.student_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = sp.student_id
                      AND h.status = 'active'
                      AND h.deadline IS NOT NULL
                      AND h.deadline < now()
                ), 0) AS overdue_homework_count,
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
                COALESCE(u.speech_style, 'formal') AS speech_style,
                (
                    SELECT sg.id
                    FROM student_groups sg
                    WHERE sg.primary_student_id = u.telegram_id
                      AND sg.group_type = 'pair'
                      AND sg.is_active = true
                    ORDER BY sg.created_at DESC, sg.id DESC
                    LIMIT 1
                ) AS pair_id,
                (
                    SELECT sg.title
                    FROM student_groups sg
                    WHERE sg.primary_student_id = u.telegram_id
                      AND sg.group_type = 'pair'
                      AND sg.is_active = true
                    ORDER BY sg.created_at DESC, sg.id DESC
                    LIMIT 1
                ) AS pair_title
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
                await conn.execute(
                    "DELETE FROM user_journey_events WHERE user_id = $1", telegram_id
                )
                await conn.execute(
                    "DELETE FROM admin_inbox WHERE payload->>'telegram_id' = $1::text",
                    telegram_id,
                )
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

    async def get_students_for_first_lesson_invite(self):
        """Students whose very first lesson has just ended and who have not yet
        received the post-first-lesson payment invite. Skips anyone with a
        confirmed payment so we don't pester paying students."""
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style,
                COALESCE(u.lesson_duration_minutes, 90) AS lesson_duration_minutes,
                first_lesson.lesson_date AS first_lesson_date,
                u.tariff_text
            FROM users u
            JOIN LATERAL (
                SELECT l.lesson_date
                FROM lessons l
                WHERE l.student_id = u.telegram_id
                  AND l.lesson_date IS NOT NULL
                ORDER BY l.lesson_date ASC
                LIMIT 1
            ) AS first_lesson ON TRUE
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
              AND COALESCE(u.first_lesson_invite_sent, false) = false
              AND first_lesson.lesson_date
                  + (COALESCE(u.lesson_duration_minutes, 90) * INTERVAL '1 minute')
                  <= NOW()
              AND NOT EXISTS (
                  SELECT 1 FROM payments p
                  WHERE p.student_id = u.telegram_id
                    AND p.status = 'confirmed'
              )
            ORDER BY first_lesson.lesson_date ASC
            """,
            fetch=True,
        )

    async def mark_first_lesson_invite_sent(self, telegram_id: int):
        await self.execute(
            """
            UPDATE users
            SET first_lesson_invite_sent = true,
                first_lesson_invite_sent_at = CURRENT_TIMESTAMP
            WHERE telegram_id = $1
            """,
            telegram_id,
            execute=True,
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

    async def get_students_for_broadcast(self):
        return await self.execute(
            """
            SELECT
                u.telegram_id,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style,
                COALESCE(u.level, '') AS level,
                COALESCE(u.lesson_format, 'online') AS lesson_format,
                u.cached_first_lesson_date,
                u.student_stage_override,
                COALESCE(SUM(p.lessons_remaining), 0)::int AS balance,
                EXISTS (
                    SELECT 1
                    FROM student_group_members sgm
                    JOIN student_groups sg ON sg.id = sgm.group_id
                    WHERE sgm.student_id = u.telegram_id
                      AND sg.group_type = 'pair'
                      AND sg.is_active = true
                ) AS is_pair
            FROM users u
            LEFT JOIN payments p
              ON p.student_id = u.telegram_id
             AND p.status = 'confirmed'
             AND p.lessons_remaining > 0
            WHERE u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            GROUP BY u.telegram_id, u.full_name, u.speech_style, u.level,
                     u.lesson_format, u.cached_first_lesson_date, u.student_stage_override
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
