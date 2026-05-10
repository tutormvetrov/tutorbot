"""User journey events: onboarding sequence storage and dispatch."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

JOURNEY_KIND_GOAL_PROMPT = "goal_prompt"
JOURNEY_KIND_MATERIALS_INTRO = "materials_intro"
JOURNEY_KIND_PREP_FIRST_LESSON = "prep_first_lesson"
JOURNEY_KIND_FEEDBACK_AFTER_FIRST = "feedback_after_first"
JOURNEY_KIND_WEEKLY_CHECKIN = "weekly_checkin"

INITIAL_JOURNEY_KINDS = (
    JOURNEY_KIND_GOAL_PROMPT,
    JOURNEY_KIND_MATERIALS_INTRO,
    JOURNEY_KIND_FEEDBACK_AFTER_FIRST,
    JOURNEY_KIND_WEEKLY_CHECKIN,
)


def _initial_schedule(registered_at: datetime) -> dict[str, datetime]:
    """When each kind should fire relative to a fresh registration."""
    base = registered_at or datetime.now()
    return {
        JOURNEY_KIND_GOAL_PROMPT: base + timedelta(hours=1),
        # Next-day morning materials intro at ~10:00 local server time.
        JOURNEY_KIND_MATERIALS_INTRO: (base + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        ),
        # Feedback fires only after the first completed lesson; we schedule
        # it 14 days out as a placeholder so the row exists and the
        # post-lesson hook can re-schedule it precisely.
        JOURNEY_KIND_FEEDBACK_AFTER_FIRST: base + timedelta(days=14),
        # Weekly check-in starts D+7 at 12:00 local.
        JOURNEY_KIND_WEEKLY_CHECKIN: (base + timedelta(days=7)).replace(
            hour=12, minute=0, second=0, microsecond=0
        ),
    }


class DatabaseJourneyMixin:
    async def set_goal_text(self, user_id: int, goal_text: str) -> None:
        await self.execute(
            """
            UPDATE users
            SET goal_text = $2,
                goal_set_at = COALESCE(goal_set_at, now())
            WHERE telegram_id = $1
            """,
            user_id,
            goal_text,
            execute=True,
        )

    async def create_initial_journey(
        self,
        user_id: int,
        registered_at: datetime | None = None,
    ) -> int:
        """Insert journey events for a freshly-registered user.

        Idempotent: existing (user_id, kind, scheduled_at) UNIQUE prevents
        duplicates if called more than once. Returns number of new rows.
        """
        schedule = _initial_schedule(registered_at or datetime.now())
        inserted = 0
        for kind in INITIAL_JOURNEY_KINDS:
            scheduled_at = schedule[kind]
            payload: dict = {}
            row = await self.execute(
                """
                INSERT INTO user_journey_events (user_id, kind, scheduled_at, payload)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (user_id, kind, scheduled_at) DO NOTHING
                RETURNING id
                """,
                user_id,
                kind,
                scheduled_at,
                json.dumps(payload, ensure_ascii=False, default=str),
                fetchval=True,
            )
            if row:
                inserted += 1
        return inserted

    async def get_due_journey_events(self, *, limit: int = 50) -> list[dict]:
        rows = await self.execute(
            """
            SELECT e.id, e.user_id, e.kind, e.scheduled_at, e.sent_at,
                   e.dismissed_at, e.payload, e.created_at
            FROM user_journey_events e
            JOIN users u ON u.telegram_id = e.user_id
            WHERE e.sent_at IS NULL
              AND e.dismissed_at IS NULL
              AND e.scheduled_at <= now()
              AND (u.frozen_until IS NULL OR u.frozen_until < NOW())
            ORDER BY e.scheduled_at
            LIMIT $1
            """,
            limit,
            fetch=True,
        )
        return [dict(r) for r in (rows or [])]

    async def mark_journey_event_sent(self, event_id: int) -> None:
        await self.execute(
            "UPDATE user_journey_events SET sent_at = now() WHERE id = $1",
            event_id,
            execute=True,
        )

    async def dismiss_journey_event(self, event_id: int) -> None:
        await self.execute(
            "UPDATE user_journey_events SET dismissed_at = now() WHERE id = $1",
            event_id,
            execute=True,
        )

    async def schedule_next_weekly_checkin(self, user_id: int, after: datetime | None = None) -> None:
        next_at = (after or datetime.now()) + timedelta(days=7)
        next_at = next_at.replace(hour=12, minute=0, second=0, microsecond=0)
        await self.execute(
            """
            INSERT INTO user_journey_events (user_id, kind, scheduled_at, payload)
            VALUES ($1, $2, $3, '{}'::jsonb)
            ON CONFLICT (user_id, kind, scheduled_at) DO NOTHING
            """,
            user_id,
            JOURNEY_KIND_WEEKLY_CHECKIN,
            next_at,
            execute=True,
        )

    async def get_journey_progress(self, user_id: int) -> dict:
        """Return the 4 onboarding steps with done/pending status.

        Steps:
          - level_test: done when users.level != 'unknown'
          - goal: done when users.goal_text IS NOT NULL
          - materials: done when materials_intro.sent_at IS NOT NULL
          - first_lesson: done when first_lesson_invite_sent = TRUE
        """
        user = await self.execute(
            """
            SELECT level, goal_text, first_lesson_invite_sent, registration_date,
                   onboarding_completed_at
            FROM users
            WHERE telegram_id = $1
            """,
            user_id,
            fetchrow=True,
        )
        if not user:
            return {
                "level_test": False,
                "goal": False,
                "materials": False,
                "first_lesson": False,
                "completed": False,
                "registered_at": None,
            }
        materials_sent = await self.execute(
            """
            SELECT sent_at IS NOT NULL
            FROM user_journey_events
            WHERE user_id = $1 AND kind = $2
            ORDER BY scheduled_at
            LIMIT 1
            """,
            user_id,
            JOURNEY_KIND_MATERIALS_INTRO,
            fetchval=True,
        )
        return {
            "level_test": (user["level"] or "").lower() != "unknown" and bool(user["level"]),
            "goal": bool(user["goal_text"]),
            "materials": bool(materials_sent),
            "first_lesson": bool(user["first_lesson_invite_sent"]),
            "completed": bool(user["onboarding_completed_at"]),
            "registered_at": user["registration_date"],
        }

    async def mark_onboarding_completed(self, user_id: int) -> bool:
        result = await self.execute(
            """
            UPDATE users
            SET onboarding_completed_at = now()
            WHERE telegram_id = $1 AND onboarding_completed_at IS NULL
            """,
            user_id,
            execute=True,
        )
        try:
            return int((result or "UPDATE 0").split()[-1]) > 0
        except Exception:
            return False

    # ─── Pair shared goal ────────────────────────────────────────────────────

    async def set_pair_goal(self, pair_id: int, goal_text: str) -> bool:
        result = await self.execute(
            """
            UPDATE student_groups
            SET shared_goal_text = $2,
                shared_goal_set_at = COALESCE(shared_goal_set_at, now())
            WHERE id = $1 AND is_active = true
            """,
            pair_id,
            goal_text,
            execute=True,
        )
        try:
            return int((result or "UPDATE 0").split()[-1]) > 0
        except Exception:
            return False

    async def get_pair_progress(self, pair_id: int, *, since: datetime | None = None) -> dict:
        """Aggregate basic pair stats since `since` (defaults to last 7 days).

        Returns dict with: lessons_completed, homework_done, payments_total,
        balance, next_lesson_at, member_telegram_ids.
        """
        if since is None:
            since = datetime.now() - timedelta(days=7)

        pair_row = await self.execute(
            """
            SELECT id, primary_student_id, shared_goal_text, shared_goal_set_at, shared_goal_due_date
            FROM student_groups WHERE id = $1
            """,
            pair_id,
            fetchrow=True,
        )
        if not pair_row:
            return {}
        primary_id = int(pair_row["primary_student_id"])

        lessons_completed = await self.execute(
            """
            SELECT COUNT(*)::int FROM lessons
            WHERE student_id = $1 AND status = 'completed' AND lesson_date >= $2
            """,
            primary_id,
            since,
            fetchval=True,
        )
        next_row = await self.execute(
            """
            SELECT lesson_date FROM lessons
            WHERE student_id = $1 AND status = 'active' AND lesson_date > now()
            ORDER BY lesson_date LIMIT 1
            """,
            primary_id,
            fetchrow=True,
        )
        homework_done = await self.execute(
            """
            SELECT COUNT(*)::int FROM homework
            WHERE student_id = $1 AND status = 'done' AND created_at >= $2
            """,
            primary_id,
            since,
            fetchval=True,
        )
        member_rows = await self.execute(
            """
            SELECT student_id FROM student_group_members
            WHERE group_id = $1 AND student_id IS NOT NULL
            """,
            pair_id,
            fetch=True,
        )
        member_ids = {primary_id, *(int(r["student_id"]) for r in (member_rows or []))}

        return {
            "pair_id": pair_id,
            "primary_id": primary_id,
            "shared_goal_text": pair_row["shared_goal_text"],
            "shared_goal_set_at": pair_row["shared_goal_set_at"],
            "lessons_completed": int(lessons_completed or 0),
            "homework_done": int(homework_done or 0),
            "next_lesson_at": next_row["lesson_date"] if next_row else None,
            "member_telegram_ids": sorted(member_ids),
            "since": since,
        }

    async def list_active_pairs(self) -> list[dict]:
        rows = await self.execute(
            """
            SELECT id, primary_student_id, title, shared_goal_text
            FROM student_groups
            WHERE is_active = true
            """,
            fetch=True,
        )
        return [dict(r) for r in (rows or [])]
