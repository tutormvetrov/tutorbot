import re


def _plain_preview(value: str | None, limit: int = 120) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class DatabaseStudyPlanMixin:
    async def publish_learning_plan(
        self,
        student_id: int,
        *,
        summary: str,
        parsed_text: str,
        parser_status: str,
        parser_warnings: str,
        file_id: str,
        file_unique_id: str | None,
        file_name: str | None,
        mime_type: str | None,
        created_by: int | None,
    ) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE student_learning_plans
                    SET status = 'archived',
                        archived_at = CURRENT_TIMESTAMP
                    WHERE student_id = $1
                      AND status = 'active'
                    """,
                    student_id,
                )
                plan_id = await conn.fetchval(
                    """
                    INSERT INTO student_learning_plans (
                        student_id,
                        status,
                        summary,
                        parsed_text,
                        parser_status,
                        parser_warnings,
                        file_id,
                        file_unique_id,
                        file_name,
                        mime_type,
                        created_by,
                        published_at
                    )
                    VALUES ($1, 'active', $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    student_id,
                    summary,
                    parsed_text,
                    parser_status,
                    parser_warnings,
                    file_id,
                    file_unique_id,
                    file_name,
                    mime_type,
                    created_by,
                )
        return int(plan_id)

    async def get_active_learning_plan(self, student_id: int):
        return await self.execute(
            """
            SELECT *
            FROM student_learning_plans
            WHERE student_id = $1
              AND status = 'active'
            ORDER BY published_at DESC, id DESC
            LIMIT 1
            """,
            student_id,
            fetchrow=True,
        )

    async def get_learning_plan_by_id(self, plan_id: int):
        return await self.execute(
            "SELECT * FROM student_learning_plans WHERE id = $1",
            plan_id,
            fetchrow=True,
        )

    async def get_learning_plan_history(self, student_id: int, limit: int = 5):
        return await self.execute(
            """
            SELECT *
            FROM student_learning_plans
            WHERE student_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            student_id,
            limit,
            fetch=True,
        )

    async def get_study_plan_recipients(self, student_id: int) -> list[int]:
        recipients = {int(student_id)}
        get_pair = getattr(self, "get_student_pair_for_student", None)
        if not callable(get_pair):
            return sorted(recipients)
        pair = await get_pair(student_id)
        if not pair:
            return sorted(recipients)
        rows = await self.execute(
            """
            SELECT student_id
            FROM student_group_members
            WHERE group_id = $1
              AND student_id IS NOT NULL
            """,
            pair["id"],
            fetch=True,
        )
        recipients.add(int(pair["primary_student_id"]))
        for row in rows or []:
            recipients.add(int(row["student_id"]))
        return sorted(recipients)

    async def get_next_study_plan_lesson(self, student_id: int):
        return await self.execute(
            """
            SELECT l.*, COALESCE(u.lesson_format, 'online') AS lesson_format
            FROM lessons l
            JOIN users u ON u.telegram_id = l.student_id
            WHERE l.student_id = $1
              AND l.status = 'active'
              AND l.lesson_date IS NOT NULL
              AND l.lesson_date >= NOW()
            ORDER BY l.lesson_date ASC, l.created_at ASC
            LIMIT 1
            """,
            student_id,
            fetchrow=True,
        )

    async def ensure_study_plan_checklist(self, student_id: int):
        lesson = await self.get_next_study_plan_lesson(student_id)
        if not lesson:
            return {"lesson": None, "items": []}

        existing = await self.execute(
            """
            SELECT *
            FROM study_plan_checklist_items
            WHERE student_id = $1
              AND lesson_id = $2
            ORDER BY sort_order ASC, id ASC
            """,
            student_id,
            lesson["id"],
            fetch=True,
        )
        if existing:
            return {"lesson": lesson, "items": list(existing)}

        auto_items = await self._build_auto_study_plan_items(student_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for order, title in enumerate(auto_items, start=1):
                    await conn.execute(
                        """
                        INSERT INTO study_plan_checklist_items (
                            student_id,
                            lesson_id,
                            title,
                            source,
                            status,
                            sort_order
                        )
                        VALUES ($1, $2, $3, 'auto', 'pending', $4)
                        """,
                        student_id,
                        lesson["id"],
                        title,
                        order,
                    )

        items = await self.execute(
            """
            SELECT *
            FROM study_plan_checklist_items
            WHERE student_id = $1
              AND lesson_id = $2
            ORDER BY sort_order ASC, id ASC
            """,
            student_id,
            lesson["id"],
            fetch=True,
        )
        return {"lesson": lesson, "items": list(items or [])}

    async def _build_auto_study_plan_items(self, student_id: int) -> list[str]:
        items: list[str] = []
        homework = list(await self.get_student_homework(student_id, "active") or [])
        if homework:
            label = "Открыть и выполнить активное ДЗ"
            if len(homework) > 1:
                label += f" ({len(homework)} задания)"
            items.append(label)

        student = await self.get_user(student_id)
        bookmark_state = (student or {}).get("current_bookmark_state")
        bookmark_text = _plain_preview((student or {}).get("current_bookmark_text"))
        if bookmark_state == "saved" and bookmark_text:
            items.append(f"Повторить текущую закладку: {bookmark_text}")
        else:
            items.append("Повторить материалы прошлого урока")

        items.append("Подготовить один вопрос к следующему уроку")
        return items

    async def add_teacher_checklist_item(self, student_id: int, title: str):
        lesson = await self.get_next_study_plan_lesson(student_id)
        lesson_id = lesson["id"] if lesson else None
        max_order = await self.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0)
            FROM study_plan_checklist_items
            WHERE student_id = $1
              AND (($2::integer IS NULL AND lesson_id IS NULL) OR lesson_id = $2)
            """,
            student_id,
            lesson_id,
            fetchval=True,
        )
        return await self.execute(
            """
            INSERT INTO study_plan_checklist_items (
                student_id,
                lesson_id,
                title,
                source,
                status,
                sort_order
            )
            VALUES ($1, $2, $3, 'teacher', 'pending', $4)
            RETURNING id
            """,
            student_id,
            lesson_id,
            title,
            int(max_order or 0) + 1,
            fetchval=True,
        )

    async def toggle_study_plan_checklist_item(self, item_id: int, student_id: int):
        item = await self.execute(
            """
            SELECT *
            FROM study_plan_checklist_items
            WHERE id = $1
              AND student_id = $2
            """,
            item_id,
            student_id,
            fetchrow=True,
        )
        if not item:
            return None
        new_status = "pending" if item["status"] == "done" else "done"
        return await self.execute(
            """
            UPDATE study_plan_checklist_items
            SET status = $3,
                completed_at = CASE WHEN $3 = 'done' THEN CURRENT_TIMESTAMP ELSE NULL END
            WHERE id = $1
              AND student_id = $2
            RETURNING *
            """,
            item_id,
            student_id,
            new_status,
            fetchrow=True,
        )

    async def upsert_pricing_rate(
        self,
        group_size: int,
        duration_minutes: int,
        amount: float,
        currency: str = "RUB",
        label: str = "",
    ) -> int:
        if label:
            # Try update by label first
            existing = await self.execute(
                "SELECT id FROM lesson_pricing_rates WHERE label = $1 AND is_active = true",
                label,
                fetchval=True,
            )
            if existing:
                await self.execute(
                    """
                    UPDATE lesson_pricing_rates
                    SET group_size = $1, duration_minutes = $2, amount = $3,
                        currency = $4, updated_at = CURRENT_TIMESTAMP
                    WHERE label = $5 AND is_active = true
                    """,
                    group_size, duration_minutes, amount, currency, label,
                    execute=True,
                )
                return existing
        return await self.execute(
            """
            INSERT INTO lesson_pricing_rates (
                group_size, duration_minutes, amount, currency, label,
                is_active, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, true, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            group_size,
            duration_minutes,
            amount,
            currency,
            label,
            fetchval=True,
        )

    async def get_pricing_rates(self):
        return await self.execute(
            """
            SELECT *
            FROM lesson_pricing_rates
            WHERE is_active = true
            ORDER BY group_size ASC, duration_minutes ASC, label ASC
            """,
            fetch=True,
        )

    async def get_pricing_rate(self, group_size: int, duration_minutes: int):
        return await self.execute(
            """
            SELECT *
            FROM lesson_pricing_rates
            WHERE group_size = $1
              AND duration_minutes = $2
              AND is_active = true
            ORDER BY id ASC
            LIMIT 1
            """,
            group_size,
            duration_minutes,
            fetchrow=True,
        )

    async def get_pricing_rate_by_id(self, rate_id: int):
        return await self.execute(
            """
            SELECT *
            FROM lesson_pricing_rates
            WHERE id = $1 AND is_active = true
            """,
            rate_id,
            fetchrow=True,
        )

    async def assign_pricing_rate(self, student_id: int, rate_id: int | None):
        await self.execute(
            "UPDATE users SET pricing_rate_id = $1 WHERE telegram_id = $2",
            rate_id, student_id,
            execute=True,
        )

    async def delete_pricing_rate(self, rate_id: int):
        await self.execute(
            "UPDATE lesson_pricing_rates SET is_active = false, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
            rate_id,
            execute=True,
        )
        # Unlink students who were on this rate
        await self.execute(
            "UPDATE users SET pricing_rate_id = NULL WHERE pricing_rate_id = $1",
            rate_id,
            execute=True,
        )

    async def get_student_pricing_context(self, student_id: int):
        user = await self.get_user(student_id)
        if not user:
            return {"group_size": 1, "duration_minutes": 90, "rate": None}

        # If student has an assigned rate, use it directly
        rate_id = user.get("pricing_rate_id")
        if rate_id:
            rate = await self.get_pricing_rate_by_id(rate_id)
            if rate:
                return {
                    "group_size": int(rate.get("group_size") or 1),
                    "duration_minutes": int(rate.get("duration_minutes") or 90),
                    "rate": rate,
                }

        # Fallback: lookup by group_size + duration
        duration = int(user.get("lesson_duration_minutes") or 90)
        group_size = 1
        get_pair = getattr(self, "get_student_pair_for_student", None)
        if callable(get_pair):
            pair = await get_pair(student_id)
            if pair:
                members = pair.get("member_names") or []
                group_size = max(2, len(members) or 2)
                primary = await self.get_user(int(pair["primary_student_id"]))
                duration = int((primary or {}).get("lesson_duration_minutes") or duration)
        rate = await self.get_pricing_rate(group_size, duration)
        return {
            "group_size": group_size,
            "duration_minutes": duration,
            "rate": rate,
        }

    async def get_learning_plan_weekly_student_rows(self):
        return await self.execute(
            """
            WITH next_lessons AS (
                SELECT DISTINCT ON (l.student_id)
                    l.student_id,
                    l.lesson_date
                FROM lessons l
                WHERE l.status = 'active'
                  AND l.lesson_date IS NOT NULL
                  AND l.lesson_date >= NOW()
                ORDER BY l.student_id, l.lesson_date ASC
            ),
            checklist AS (
                SELECT
                    student_id,
                    COUNT(*)::int AS total_items,
                    COUNT(*) FILTER (WHERE status = 'done')::int AS done_items
                FROM study_plan_checklist_items
                GROUP BY student_id
            )
            SELECT
                u.telegram_id AS student_id,
                u.full_name,
                p.id AS plan_id,
                p.summary,
                p.file_name,
                n.lesson_date AS next_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = u.telegram_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE(c.total_items, 0) AS checklist_total,
                COALESCE(c.done_items, 0) AS checklist_done
            FROM student_learning_plans p
            JOIN users u ON u.telegram_id = p.student_id
            LEFT JOIN next_lessons n ON n.student_id = p.student_id
            LEFT JOIN checklist c ON c.student_id = p.student_id
            WHERE p.status = 'active'
              AND u.role = 'student'
              AND u.is_active = true
              AND COALESCE(u.is_internal_account, false) = false
            ORDER BY u.full_name
            """,
            fetch=True,
        )

    async def get_learning_plan_parent_digest_rows(self):
        return await self.execute(
            """
            WITH child_plan AS (
                SELECT
                    sp.id AS link_id,
                    sp.parent_id,
                    sp.student_id,
                    COALESCE(g.primary_student_id, sp.student_id) AS plan_student_id
                FROM student_parent sp
                LEFT JOIN student_group_members gm ON gm.student_id = sp.student_id
                LEFT JOIN student_groups g ON g.id = gm.group_id AND g.is_active = true
                WHERE sp.is_active = true
                  AND sp.student_id IS NOT NULL
            ),
            next_lessons AS (
                SELECT DISTINCT ON (l.student_id)
                    l.student_id,
                    l.lesson_date
                FROM lessons l
                WHERE l.status = 'active'
                  AND l.lesson_date IS NOT NULL
                  AND l.lesson_date >= NOW()
                ORDER BY l.student_id, l.lesson_date ASC
            ),
            checklist AS (
                SELECT
                    student_id,
                    COUNT(*)::int AS total_items,
                    COUNT(*) FILTER (WHERE status = 'done')::int AS done_items
                FROM study_plan_checklist_items
                GROUP BY student_id
            )
            SELECT
                cp.link_id,
                cp.parent_id,
                cp.student_id,
                cp.plan_student_id,
                parent.full_name AS parent_name,
                student.full_name AS student_name,
                p.id AS plan_id,
                p.summary,
                n.lesson_date AS next_lesson_date,
                COALESCE((
                    SELECT COUNT(*)::int
                    FROM homework h
                    WHERE h.student_id = cp.plan_student_id
                      AND h.status = 'active'
                ), 0) AS active_homework_count,
                COALESCE(c.total_items, 0) AS checklist_total,
                COALESCE(c.done_items, 0) AS checklist_done
            FROM child_plan cp
            JOIN users parent ON parent.telegram_id = cp.parent_id
            JOIN users student ON student.telegram_id = cp.student_id
            JOIN student_learning_plans p ON p.student_id = cp.plan_student_id AND p.status = 'active'
            LEFT JOIN next_lessons n ON n.student_id = cp.plan_student_id
            LEFT JOIN checklist c ON c.student_id = cp.plan_student_id
            WHERE parent.role = 'parent'
              AND parent.is_active = true
              AND student.role = 'student'
              AND student.is_active = true
            ORDER BY parent.full_name, student.full_name
            """,
            fetch=True,
        )
