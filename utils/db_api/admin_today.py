import asyncio
from datetime import datetime


class DatabaseAdminTodayMixin:
    """Mixin that aggregates data for the «🎯 Сегодня» admin dashboard screen."""

    async def get_admin_today_snapshot(
        self,
        today_start: datetime,
        tomorrow_start: datetime,
    ) -> dict:
        """
        Return a dict with all counters needed for the «Сегодня» screen.

        Fields:
          lessons_today       - list of {time, full_name, lesson_format}
          unpaid_count        - students with lesson_balance == 0
          missing_homework_count - lessons within 24h that have no HW set
          pending_freeze_count   - freeze_pending lessons awaiting admin action
          unanswered_replies_count - placeholder 0 (Stage 3 wires in full Inbox)
        """
        (
            lessons_raw,
            students_with_balances,
            missing_hw,
            pending_freezes,
            unanswered_replies_count,
            hard_feedback,
        ) = await asyncio.gather(
            self.get_lessons_in_window(today_start, tomorrow_start),
            self.get_students_with_balances(),
            self.get_lessons_missing_homework(),
            self.get_pending_freeze_lessons(),
            self.count_unread_inbox(),
            self.get_hard_feedback_today(),
        )

        # Build today's lessons list, enriched with student full_name and format.
        # get_lessons_in_window returns rows with student_id only; we need names.
        # Fetch them from students_with_balances lookup (or call users table).
        # For simplicity, do a lightweight join via a second query.
        student_ids = [row["student_id"] for row in (lessons_raw or [])]
        name_map: dict[int, str] = {}
        format_map: dict[int, str] = {}
        if student_ids:
            rows = await self._get_users_by_ids(student_ids)
            for row in rows:
                tid = row["telegram_id"]
                name_map[tid] = row.get("full_name") or str(tid)
                format_map[tid] = (row.get("lesson_format") or "online").strip().lower()

        lessons_today = []
        for row in (lessons_raw or []):
            lesson_date: datetime | None = row.get("lesson_date")
            sid = row["student_id"]
            lessons_today.append({
                "time": lesson_date.strftime("%H:%M") if lesson_date else "—",
                "full_name": name_map.get(sid, str(sid)),
                "lesson_format": format_map.get(sid, "online"),
            })

        unpaid_count = sum(
            1 for s in (students_with_balances or []) if int(s.get("lesson_balance") or 0) == 0
        )

        hard_feedback_items = []
        for fb in (hard_feedback or []):
            fb_date = fb.get("lesson_date")
            date_str = fb_date.strftime("%d.%m") if fb_date else ""
            hard_feedback_items.append({
                "full_name": fb.get("full_name") or str(fb.get("user_id", "?")),
                "date": date_str,
            })

        return {
            "lessons_today": lessons_today,
            "unpaid_count": unpaid_count,
            "missing_homework_count": len(missing_hw or []),
            "pending_freeze_count": len(pending_freezes or []),
            "unanswered_replies_count": unanswered_replies_count,
            "hard_feedback": hard_feedback_items,
        }

    async def _get_users_by_ids(self, telegram_ids: list[int]) -> list:
        """Fetch minimal user info (full_name, lesson_format) for a list of IDs."""
        if not telegram_ids:
            return []
        return await self.execute(
            """
            SELECT telegram_id, full_name, COALESCE(lesson_format, 'online') AS lesson_format
            FROM users
            WHERE telegram_id = ANY($1::bigint[])
            """,
            telegram_ids,
            fetch=True,
        )
