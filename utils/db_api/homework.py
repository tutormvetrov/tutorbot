import logging
from datetime import datetime

from utils.homework_materials import parse_homework_material_mentions


logger = logging.getLogger(__name__)


class DatabaseHomeworkMixin:
    async def add_homework(
        self,
        student_id: int,
        title: str,
        description: str | None,
        deadline,
        attachment: dict | None = None,
    ):
        attachment = attachment or {}
        homework_id = await self.execute(
            """
            INSERT INTO homework (
                student_id,
                title,
                description,
                deadline,
                attachment_file_id,
                attachment_file_unique_id,
                attachment_name,
                attachment_mime_type
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            student_id,
            title,
            description,
            deadline,
            attachment.get("file_id"),
            attachment.get("file_unique_id"),
            attachment.get("file_name"),
            attachment.get("mime_type"),
            fetchval=True,
        )
        try:
            await self.save_homework_material_mentions(homework_id, student_id, description)
        except Exception as exc:
            logger.warning("Не удалось разобрать материалы для ДЗ %s: %s", homework_id, exc)
        return homework_id

    async def update_homework(
        self,
        homework_id: int,
        student_id: int,
        title: str,
        description: str | None,
        deadline,
        attachment: dict | None = None,
    ):
        attachment = attachment or {}
        await self.execute(
            """
            UPDATE homework
            SET
                title = $2,
                description = $3,
                deadline = $4,
                attachment_file_id = $5,
                attachment_file_unique_id = $6,
                attachment_name = $7,
                attachment_mime_type = $8
            WHERE id = $1
            """,
            homework_id,
            title,
            description,
            deadline,
            attachment.get("file_id"),
            attachment.get("file_unique_id"),
            attachment.get("file_name"),
            attachment.get("mime_type"),
            execute=True,
        )
        try:
            await self.save_homework_material_mentions(homework_id, student_id, description)
        except Exception as exc:
            logger.warning("Не удалось обновить материалы для ДЗ %s: %s", homework_id, exc)

    async def save_homework_material_mentions(self, homework_id: int, student_id: int, description: str | None):
        mentions = parse_homework_material_mentions(description)
        await self.execute(
            "DELETE FROM homework_material_mentions WHERE homework_id = $1",
            homework_id,
            execute=True,
        )
        for mention in mentions:
            await self.execute(
                """
                INSERT INTO homework_material_mentions (
                    homework_id,
                    student_id,
                    material_key,
                    material_title,
                    material_kind,
                    page_from,
                    page_to,
                    unit_label,
                    chapter_label,
                    lesson_label,
                    exercise_label,
                    raw_fragment
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                homework_id,
                student_id,
                mention["material_key"],
                mention["material_title"],
                mention["material_kind"],
                mention["page_from"],
                mention["page_to"],
                mention["unit_label"],
                mention["chapter_label"],
                mention["lesson_label"],
                mention["exercise_label"],
                mention["raw_fragment"],
                execute=True,
            )
        await self.execute(
            "UPDATE homework SET materials_parsed_at = NOW() WHERE id = $1",
            homework_id,
            execute=True,
        )

    async def backfill_homework_materials_for_student(self, student_id: int):
        rows = await self.execute(
            """
            SELECT id, student_id, description
            FROM homework
            WHERE student_id = $1
              AND materials_parsed_at IS NULL
            ORDER BY created_at ASC, id ASC
            """,
            student_id,
            fetch=True,
        )
        for row in rows:
            await self.save_homework_material_mentions(row["id"], row["student_id"], row["description"])
        return len(rows)

    async def has_homework_history(self, student_id: int) -> bool:
        return bool(
            await self.execute(
                "SELECT EXISTS(SELECT 1 FROM homework WHERE student_id = $1)",
                student_id,
                fetchval=True,
            )
        )

    async def get_recent_homework_material_mentions(self, student_id: int, limit: int = 3):
        return await self.execute(
            """
            SELECT
                hmm.*,
                h.created_at AS homework_created_at,
                h.deadline AS homework_deadline
            FROM homework_material_mentions hmm
            JOIN homework h ON h.id = hmm.homework_id
            WHERE hmm.student_id = $1
            ORDER BY h.created_at DESC, h.id DESC, hmm.id DESC
            LIMIT $2
            """,
            student_id,
            limit,
            fetch=True,
        )

    async def get_top_homework_materials(self, student_id: int, limit: int = 3):
        return await self.execute(
            """
            WITH ranked AS (
                SELECT
                    hmm.material_key,
                    hmm.material_title,
                    h.created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY hmm.material_key
                        ORDER BY h.created_at DESC, h.id DESC, hmm.id DESC
                    ) AS row_num
                FROM homework_material_mentions hmm
                JOIN homework h ON h.id = hmm.homework_id
                WHERE hmm.student_id = $1
            )
            SELECT
                material_key,
                MAX(material_title) FILTER (WHERE row_num = 1) AS material_title,
                COUNT(*) AS mentions_count,
                MAX(created_at) AS last_assigned_at
            FROM ranked
            GROUP BY material_key
            ORDER BY mentions_count DESC, last_assigned_at DESC, material_key ASC
            LIMIT $2
            """,
            student_id,
            limit,
            fetch=True,
        )

    async def get_latest_homework_material_mention(self, student_id: int):
        return await self.execute(
            """
            SELECT
                hmm.*,
                h.created_at AS homework_created_at,
                h.deadline AS homework_deadline
            FROM homework_material_mentions hmm
            JOIN homework h ON h.id = hmm.homework_id
            WHERE hmm.student_id = $1
            ORDER BY h.created_at DESC, h.id DESC, hmm.id DESC
            LIMIT 1
            """,
            student_id,
            fetchrow=True,
        )

    async def get_student_homework(self, student_id: int, status: str | None = None):
        if status:
            return await self.execute(
                "SELECT * FROM homework WHERE student_id=$1 AND status=$2 ORDER BY deadline ASC",
                student_id,
                status,
                fetch=True,
            )
        return await self.execute(
            "SELECT * FROM homework WHERE student_id=$1 ORDER BY deadline ASC",
            student_id,
            fetch=True,
        )

    async def get_homework_by_id(self, hw_id: int):
        return await self.execute(
            """
            SELECT
                h.*,
                q.delivery_kind AS queued_delivery_kind,
                q.deliver_after AS queued_deliver_after,
                q.include_attachment AS queued_include_attachment,
                q.last_attempt_at AS queued_last_attempt_at,
                q.attempts AS queued_attempts,
                q.last_error AS queued_last_error
            FROM homework h
            LEFT JOIN homework_delivery_queue q ON q.homework_id = h.id
            WHERE h.id = $1
            """,
            hw_id,
            fetchrow=True,
        )

    async def delete_homework(self, hw_id: int):
        await self.execute(
            "DELETE FROM homework WHERE id=$1",
            hw_id,
            execute=True,
        )

    async def mark_homework_done(self, hw_id: int, student_id: int):
        await self.execute(
            "UPDATE homework SET status='done' WHERE id=$1 AND student_id=$2 AND status='active'",
            hw_id,
            student_id,
            execute=True,
        )

    async def get_homework_due_tomorrow(self):
        return await self.execute(
            """
            SELECT h.*, u.telegram_id, u.full_name, COALESCE(u.speech_style, 'formal') AS speech_style
            FROM homework h
            JOIN users u ON u.telegram_id = h.student_id
            WHERE h.status = 'active'
              AND h.reminder_sent = false
              AND h.deadline >= NOW() + INTERVAL '20 hours'
              AND h.deadline <= NOW() + INTERVAL '28 hours'
            """,
            fetch=True,
        )

    async def mark_homework_reminder_sent(self, hw_id: int):
        await self.execute(
            "UPDATE homework SET reminder_sent=true WHERE id=$1",
            hw_id,
            execute=True,
        )

    async def get_all_active_homework(self):
        return await self.execute(
            """
            SELECT
                h.*,
                u.full_name,
                q.delivery_kind AS queued_delivery_kind,
                q.deliver_after AS queued_deliver_after,
                q.include_attachment AS queued_include_attachment,
                q.last_attempt_at AS queued_last_attempt_at,
                q.attempts AS queued_attempts,
                q.last_error AS queued_last_error
            FROM homework h
            JOIN users u ON u.telegram_id = h.student_id
            LEFT JOIN homework_delivery_queue q ON q.homework_id = h.id
            WHERE h.status = 'active'
            ORDER BY h.deadline ASC, h.id ASC
            """,
            fetch=True,
        )

    async def upsert_homework_delivery(
        self,
        homework_id: int,
        student_id: int,
        delivery_kind: str,
        deliver_after: datetime,
        *,
        include_attachment: bool = False,
    ):
        await self.execute(
            """
            INSERT INTO homework_delivery_queue (
                homework_id,
                student_id,
                delivery_kind,
                deliver_after,
                include_attachment,
                last_attempt_at,
                attempts,
                last_error
            )
            VALUES ($1, $2, $3, $4, $5, NULL, 0, NULL)
            ON CONFLICT (homework_id) DO UPDATE
            SET
                student_id = EXCLUDED.student_id,
                delivery_kind = EXCLUDED.delivery_kind,
                deliver_after = EXCLUDED.deliver_after,
                include_attachment = EXCLUDED.include_attachment,
                last_attempt_at = NULL,
                attempts = 0,
                last_error = NULL
            """,
            homework_id,
            student_id,
            delivery_kind,
            deliver_after,
            include_attachment,
            execute=True,
        )

    async def get_homework_delivery(self, homework_id: int):
        return await self.execute(
            "SELECT * FROM homework_delivery_queue WHERE homework_id = $1",
            homework_id,
            fetchrow=True,
        )

    async def clear_homework_delivery(self, homework_id: int):
        await self.execute(
            "DELETE FROM homework_delivery_queue WHERE homework_id = $1",
            homework_id,
            execute=True,
        )

    async def mark_homework_delivery_failure(self, homework_id: int, attempted_at: datetime, error: str):
        await self.execute(
            """
            UPDATE homework_delivery_queue
            SET
                last_attempt_at = $2,
                attempts = attempts + 1,
                last_error = $3
            WHERE homework_id = $1
            """,
            homework_id,
            attempted_at,
            error,
            execute=True,
        )

    async def get_due_homework_deliveries(self, due_before: datetime, retry_before: datetime):
        return await self.execute(
            """
            SELECT
                h.*,
                q.id AS queue_id,
                q.delivery_kind,
                q.deliver_after,
                q.include_attachment,
                q.last_attempt_at,
                q.attempts,
                q.last_error,
                q.created_at AS queue_created_at,
                u.full_name,
                COALESCE(u.speech_style, 'formal') AS speech_style
            FROM homework_delivery_queue q
            JOIN homework h ON h.id = q.homework_id
            JOIN users u ON u.telegram_id = q.student_id
            WHERE q.deliver_after <= $1
              AND (q.last_attempt_at IS NULL OR q.last_attempt_at <= $2)
              AND h.status = 'active'
            ORDER BY q.student_id ASC, q.deliver_after ASC, h.deadline ASC, h.id ASC
            """,
            due_before,
            retry_before,
            fetch=True,
        )
