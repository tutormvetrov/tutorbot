import logging


logger = logging.getLogger(__name__)


class DatabaseSchemaMixin:
    def _log_migration_failure(self, migration_name: str, exc: Exception):
        logger.error("Schema migration failed: %s: %s", migration_name, exc)

    async def create_table_users(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL UNIQUE,
                full_name VARCHAR(255) NOT NULL,
                username VARCHAR(255),
                role VARCHAR(50) NOT NULL,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT true,
                lesson_duration_minutes INTEGER DEFAULT 90,
                current_bookmark_text TEXT,
                current_bookmark_state TEXT DEFAULT 'empty',
                current_bookmark_updated_at TIMESTAMP,
                current_bookmark_lesson_id INTEGER
            );
        """, execute=True)

    async def create_table_student_parent(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS student_parent (
                id SERIAL PRIMARY KEY,
                student_id BIGINT REFERENCES users(telegram_id),
                parent_id BIGINT REFERENCES users(telegram_id),
                student_info TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_student_groups(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS student_groups (
                id SERIAL PRIMARY KEY,
                group_type TEXT NOT NULL DEFAULT 'pair',
                title TEXT NOT NULL,
                primary_student_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                balance_mode TEXT NOT NULL DEFAULT 'shared',
                homework_mode TEXT NOT NULL DEFAULT 'shared',
                onboarding_source TEXT DEFAULT 'admin',
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)
        await self.execute("""
            CREATE TABLE IF NOT EXISTS student_group_members (
                id SERIAL PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
                student_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
                member_name TEXT NOT NULL,
                member_role TEXT NOT NULL DEFAULT 'partner',
                has_bot_access BOOLEAN DEFAULT false,
                invite_token TEXT UNIQUE,
                invite_created_at TIMESTAMP,
                invite_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS student_groups_primary_student_idx
            ON student_groups (primary_student_id)
            WHERE is_active = true;
            """,
            execute=True,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS student_group_members_group_id_idx
            ON student_group_members (group_id);
            """,
            execute=True,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS student_group_members_student_id_idx
            ON student_group_members (student_id)
            WHERE student_id IS NOT NULL;
            """,
            execute=True,
        )

    async def create_table_blocked_telegram_ids(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS blocked_telegram_ids (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL UNIQUE,
                reason TEXT,
                blocked_by BIGINT,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                previous_is_active BOOLEAN
            );
        """, execute=True)

    async def create_table_lessons(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id SERIAL PRIMARY KEY,
                student_id BIGINT REFERENCES users(telegram_id),
                google_event_id TEXT,
                lesson_date TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                freeze_start_date TIMESTAMP,
                freeze_end_date TIMESTAMP,
                freeze_reason TEXT,
                teacher_followup_sent BOOLEAN DEFAULT false,
                teacher_pre_lesson_note_sent BOOLEAN DEFAULT false,
                teacher_comment TEXT,
                teacher_comment_saved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_homework(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id SERIAL PRIMARY KEY,
                student_id BIGINT REFERENCES users(telegram_id),
                title VARCHAR(255) NOT NULL,
                description TEXT,
                deadline TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                reminder_sent BOOLEAN DEFAULT false,
                attachment_file_id TEXT,
                attachment_file_unique_id TEXT,
                attachment_name TEXT,
                attachment_mime_type TEXT,
                materials_parsed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_homework_delivery_queue(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS homework_delivery_queue (
                id SERIAL PRIMARY KEY,
                homework_id INTEGER NOT NULL UNIQUE REFERENCES homework(id) ON DELETE CASCADE,
                student_id BIGINT NOT NULL REFERENCES users(telegram_id),
                delivery_kind TEXT NOT NULL,
                deliver_after TIMESTAMP NOT NULL,
                include_attachment BOOLEAN DEFAULT false,
                last_attempt_at TIMESTAMP,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS homework_delivery_queue_deliver_after_idx
            ON homework_delivery_queue (deliver_after);
            """,
            execute=True,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS homework_delivery_queue_student_after_idx
            ON homework_delivery_queue (student_id, deliver_after);
            """,
            execute=True,
        )

    async def create_table_homework_material_mentions(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS homework_material_mentions (
                id SERIAL PRIMARY KEY,
                homework_id INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
                student_id BIGINT NOT NULL REFERENCES users(telegram_id),
                material_key TEXT NOT NULL,
                material_title TEXT NOT NULL,
                material_kind TEXT NOT NULL DEFAULT 'book',
                page_from INTEGER,
                page_to INTEGER,
                unit_label TEXT,
                chapter_label TEXT,
                lesson_label TEXT,
                exercise_label TEXT,
                raw_fragment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_payments(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                payer_id BIGINT REFERENCES users(telegram_id),
                student_id BIGINT REFERENCES users(telegram_id),
                amount DECIMAL(10,2) NOT NULL,
                lessons_count INTEGER NOT NULL,
                lessons_remaining INTEGER NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                payment_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)

    async def create_table_learning_plans(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS student_learning_plans (
                id SERIAL PRIMARY KEY,
                student_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'active',
                summary TEXT,
                parsed_text TEXT,
                parser_status TEXT DEFAULT 'ok',
                parser_warnings TEXT,
                file_id TEXT NOT NULL,
                file_unique_id TEXT,
                file_name TEXT,
                mime_type TEXT,
                created_by BIGINT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                archived_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)
        await self.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS student_learning_plans_one_active_idx
            ON student_learning_plans (student_id)
            WHERE status = 'active';
            """,
            execute=True,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS student_learning_plans_student_status_idx
            ON student_learning_plans (student_id, status, created_at DESC);
            """,
            execute=True,
        )
        await self.execute("""
            CREATE TABLE IF NOT EXISTS study_plan_checklist_items (
                id SERIAL PRIMARY KEY,
                student_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'auto',
                status TEXT NOT NULL DEFAULT 'pending',
                sort_order INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS study_plan_checklist_student_lesson_idx
            ON study_plan_checklist_items (student_id, lesson_id, sort_order, id);
            """,
            execute=True,
        )

    async def create_table_lesson_pricing_rates(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS lesson_pricing_rates (
                id SERIAL PRIMARY KEY,
                group_size INTEGER NOT NULL,
                duration_minutes INTEGER NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB',
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (group_size, duration_minutes)
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS lesson_pricing_rates_lookup_idx
            ON lesson_pricing_rates (group_size, duration_minutes)
            WHERE is_active = true;
            """,
            execute=True,
        )

    async def create_table_calendar_student_links(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS calendar_student_links (
                id SERIAL PRIMARY KEY,
                student_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                calendar_alias TEXT,
                calendar_event_pattern TEXT,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT calendar_student_links_match_check
                    CHECK (
                        COALESCE(NULLIF(BTRIM(calendar_alias), ''), NULL) IS NOT NULL
                        OR COALESCE(NULLIF(BTRIM(calendar_event_pattern), ''), NULL) IS NOT NULL
                    )
            );
        """, execute=True)

    async def migrate_lessons_google_event_id(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ALTER COLUMN google_event_id DROP NOT NULL;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_google_event_id", exc)
            return

    async def migrate_lessons_add_date(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS lesson_date TIMESTAMP;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_date", exc)
            return

    async def migrate_lessons_google_event_id_unique(self):
        try:
            index_def = await self.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'lessons'
                  AND indexname = 'lessons_google_event_id_idx'
                """,
                fetchval=True,
            )
            if index_def and " WHERE " in index_def.upper():
                await self.execute(
                    "DROP INDEX IF EXISTS lessons_google_event_id_idx;",
                    execute=True,
                )
            await self.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS lessons_google_event_id_idx
                ON lessons (google_event_id);
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_google_event_id_unique", exc)
            return

    async def migrate_lessons_add_reminder_sent(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT false;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_reminder_sent", exc)
            return

    async def migrate_users_add_language_level(self):
        for col, definition in [
            ("language", "TEXT"),
            ("level", "TEXT"),
            ("age", "INTEGER"),
            ("review_sent", "BOOLEAN DEFAULT false"),
            ("lesson_reminders", "TEXT DEFAULT 'enabled'"),
            ("is_internal_account", "BOOLEAN DEFAULT false"),
        ]:
            try:
                await self.execute(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition};",
                    execute=True,
                )
            except Exception as exc:
                self._log_migration_failure(f"migrate_users_add_language_level:{col}", exc)
                return

    async def migrate_users_add_lesson_format(self):
        try:
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS lesson_format TEXT DEFAULT 'online';",
                execute=True,
            )
            await self.execute(
                "UPDATE users SET lesson_format = 'online' WHERE lesson_format IS NULL OR lesson_format = '';",
                execute=True,
            )
            await self.execute(
                """
                UPDATE users
                SET lesson_format = 'offline'
                WHERE role = 'student'
                  AND LOWER(BTRIM(full_name)) IN ('мария вовк', 'георгий мартынов');
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_lesson_format", exc)
            return

    async def migrate_users_add_speech_style(self):
        try:
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS speech_style TEXT DEFAULT 'formal';",
                execute=True,
            )
            await self.execute(
                "UPDATE users SET speech_style = 'formal' WHERE speech_style IS NULL OR speech_style = '';",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_speech_style", exc)
            return

    async def migrate_users_add_lesson_followup_fields(self):
        try:
            for col, definition in [
                ("lesson_duration_minutes", "INTEGER DEFAULT 90"),
                ("current_bookmark_text", "TEXT"),
                ("current_bookmark_state", "TEXT DEFAULT 'empty'"),
                ("current_bookmark_updated_at", "TIMESTAMP"),
                ("current_bookmark_lesson_id", "INTEGER"),
            ]:
                await self.execute(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition};",
                    execute=True,
                )
            await self.execute(
                """
                UPDATE users
                SET lesson_duration_minutes = 90
                WHERE lesson_duration_minutes IS NULL
                """,
                execute=True,
            )
            await self.execute(
                """
                UPDATE users
                SET current_bookmark_state = 'empty'
                WHERE current_bookmark_state IS NULL
                   OR BTRIM(current_bookmark_state) = ''
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_lesson_followup_fields", exc)
            return

    async def migrate_internal_test_accounts(self):
        try:
            from data import config

            rows = await self.execute(
                "SELECT telegram_id, full_name, username FROM users",
                fetch=True,
            )
            for row in rows:
                is_internal = config.is_internal_test_account(
                    full_name=row["full_name"] or "",
                    username=row["username"] or "",
                    telegram_id=row["telegram_id"],
                )
                await self.execute(
                    "UPDATE users SET is_internal_account = $2 WHERE telegram_id = $1",
                    row["telegram_id"], is_internal, execute=True,
                )
        except Exception as exc:
            self._log_migration_failure("migrate_internal_test_accounts", exc)
            return

    async def migrate_lessons_add_balance_consumed(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS balance_consumed BOOLEAN DEFAULT false;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_balance_consumed", exc)
            return

    async def migrate_lessons_add_homework_check_flag(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS homework_check_reminder_sent BOOLEAN DEFAULT false;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_homework_check_flag", exc)
            return

    async def migrate_lessons_add_source(self):
        try:
            await self.execute(
                "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';",
                execute=True,
            )
            await self.execute(
                "UPDATE lessons SET source = 'manual' WHERE source IS NULL;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_source", exc)
            return

    async def migrate_lessons_add_teacher_followup_fields(self):
        try:
            for col, definition in [
                ("teacher_followup_sent", "BOOLEAN DEFAULT false"),
                ("teacher_pre_lesson_note_sent", "BOOLEAN DEFAULT false"),
                ("teacher_comment", "TEXT"),
                ("teacher_comment_saved_at", "TIMESTAMP"),
            ]:
                await self.execute(
                    f"ALTER TABLE lessons ADD COLUMN IF NOT EXISTS {col} {definition};",
                    execute=True,
                )
            await self.execute(
                """
                UPDATE lessons
                SET teacher_followup_sent = false
                WHERE teacher_followup_sent IS NULL
                """,
                execute=True,
            )
            await self.execute(
                """
                UPDATE lessons
                SET teacher_pre_lesson_note_sent = false
                WHERE teacher_pre_lesson_note_sent IS NULL
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_lessons_add_teacher_followup_fields", exc)
            return

    async def migrate_homework_add_material_fields(self):
        try:
            await self.execute(
                "ALTER TABLE homework ADD COLUMN IF NOT EXISTS materials_parsed_at TIMESTAMP;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_homework_add_material_fields", exc)
            return

    async def migrate_homework_add_attachment_fields(self):
        try:
            for statement in [
                "ALTER TABLE homework ADD COLUMN IF NOT EXISTS attachment_file_id TEXT;",
                "ALTER TABLE homework ADD COLUMN IF NOT EXISTS attachment_file_unique_id TEXT;",
                "ALTER TABLE homework ADD COLUMN IF NOT EXISTS attachment_name TEXT;",
                "ALTER TABLE homework ADD COLUMN IF NOT EXISTS attachment_mime_type TEXT;",
            ]:
                await self.execute(statement, execute=True)
        except Exception as exc:
            self._log_migration_failure("migrate_homework_add_attachment_fields", exc)
            return

    async def migrate_homework_material_mentions_indexes(self):
        try:
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS homework_material_mentions_student_id_idx
                ON homework_material_mentions (student_id, material_key);
                """,
                execute=True,
            )
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS homework_material_mentions_homework_id_idx
                ON homework_material_mentions (homework_id);
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_homework_material_mentions_indexes", exc)
            return

    async def migrate_calendar_links_indexes(self):
        try:
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS calendar_student_links_student_id_idx
                ON calendar_student_links (student_id)
                WHERE is_active = true;
                """,
                execute=True,
            )
            await self.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS calendar_student_links_alias_unique_idx
                ON calendar_student_links (student_id, LOWER(COALESCE(calendar_alias, '')), LOWER(COALESCE(calendar_event_pattern, '')))
                WHERE is_active = true;
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_calendar_links_indexes", exc)
            return

    async def migrate_student_group_member_invites(self):
        try:
            for statement in [
                "ALTER TABLE student_group_members ADD COLUMN IF NOT EXISTS invite_token TEXT UNIQUE;",
                "ALTER TABLE student_group_members ADD COLUMN IF NOT EXISTS invite_created_at TIMESTAMP;",
                "ALTER TABLE student_group_members ADD COLUMN IF NOT EXISTS invite_used_at TIMESTAMP;",
            ]:
                await self.execute(statement, execute=True)
        except Exception as exc:
            self._log_migration_failure("migrate_student_group_member_invites", exc)
            return

    async def migrate_learning_plan_schema(self):
        try:
            learning_plan_columns = [
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS summary TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS parsed_text TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS parser_status TEXT DEFAULT 'ok';",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS parser_warnings TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS file_id TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS file_unique_id TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS file_name TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS mime_type TEXT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS created_by BIGINT;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;",
                "ALTER TABLE student_learning_plans ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            ]
            checklist_columns = [
                "ALTER TABLE study_plan_checklist_items ADD COLUMN IF NOT EXISTS lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL;",
                "ALTER TABLE study_plan_checklist_items ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'auto';",
                "ALTER TABLE study_plan_checklist_items ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';",
                "ALTER TABLE study_plan_checklist_items ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;",
                "ALTER TABLE study_plan_checklist_items ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;",
                "ALTER TABLE study_plan_checklist_items ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            ]
            pricing_columns = [
                "ALTER TABLE lesson_pricing_rates ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'RUB';",
                "ALTER TABLE lesson_pricing_rates ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;",
                "ALTER TABLE lesson_pricing_rates ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
                "ALTER TABLE lesson_pricing_rates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            ]
            for statement in learning_plan_columns + checklist_columns + pricing_columns:
                await self.execute(statement, execute=True)
            await self.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS student_learning_plans_one_active_idx
                ON student_learning_plans (student_id)
                WHERE status = 'active';
                """,
                execute=True,
            )
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS student_learning_plans_student_status_idx
                ON student_learning_plans (student_id, status, created_at DESC);
                """,
                execute=True,
            )
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS study_plan_checklist_student_lesson_idx
                ON study_plan_checklist_items (student_id, lesson_id, sort_order, id);
                """,
                execute=True,
            )
            await self.execute(
                """
                CREATE INDEX IF NOT EXISTS lesson_pricing_rates_lookup_idx
                ON lesson_pricing_rates (group_size, duration_minutes)
                WHERE is_active = true;
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_learning_plan_schema", exc)
            return

    async def migrate_users_add_first_lesson_invite(self):
        try:
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_lesson_invite_sent BOOLEAN DEFAULT false;",
                execute=True,
            )
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_lesson_invite_sent_at TIMESTAMP;",
                execute=True,
            )
            # Backfill: existing students that already have a completed lesson must not
            # receive a retroactive "thank you for your first lesson" message.
            await self.execute(
                """
                UPDATE users u
                SET first_lesson_invite_sent = true,
                    first_lesson_invite_sent_at = COALESCE(first_lesson_invite_sent_at, CURRENT_TIMESTAMP)
                WHERE COALESCE(first_lesson_invite_sent, false) = false
                  AND EXISTS (
                      SELECT 1 FROM lessons l
                      WHERE l.student_id = u.telegram_id
                        AND l.status = 'completed'
                  )
                """,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_first_lesson_invite", exc)
            return

    async def create_table_admin_inbox(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS admin_inbox (
                id SERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT now(),
                read_at TIMESTAMP,
                handled_at TIMESTAMP,
                handled_by BIGINT
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS admin_inbox_unread_idx
            ON admin_inbox (created_at DESC)
            WHERE handled_at IS NULL;
            """,
            execute=True,
        )

    async def migrate_admin_inbox(self):
        try:
            await self.create_table_admin_inbox()
        except Exception as exc:
            self._log_migration_failure("migrate_admin_inbox", exc)
            return

    async def migrate_users_add_onboarding(self):
        try:
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_text TEXT;",
                execute=True,
            )
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS goal_set_at TIMESTAMP;",
                execute=True,
            )
            await self.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMP;",
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_users_add_onboarding", exc)
            return

    async def create_table_user_journey_events(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS user_journey_events (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                kind TEXT NOT NULL,
                scheduled_at TIMESTAMP NOT NULL,
                sent_at TIMESTAMP,
                dismissed_at TIMESTAMP,
                payload JSONB,
                created_at TIMESTAMP DEFAULT now(),
                UNIQUE(user_id, kind, scheduled_at)
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS user_journey_events_due_idx
            ON user_journey_events (scheduled_at)
            WHERE sent_at IS NULL AND dismissed_at IS NULL;
            """,
            execute=True,
        )
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS user_journey_events_user_idx
            ON user_journey_events (user_id, kind);
            """,
            execute=True,
        )

    async def migrate_user_journey_events(self):
        try:
            await self.create_table_user_journey_events()
        except Exception as exc:
            self._log_migration_failure("migrate_user_journey_events", exc)
            return

    async def create_table_student_resources(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS student_resources (
                id SERIAL PRIMARY KEY,
                student_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                url TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'other',
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT now(),
                created_by BIGINT
            );
        """, execute=True)
        await self.execute(
            """
            CREATE INDEX IF NOT EXISTS student_resources_student_idx
            ON student_resources (student_id, is_primary DESC, sort_order);
            """,
            execute=True,
        )
        # At most one primary per student (NULL student_id treated as the
        # global owner via COALESCE with sentinel -1, which Telegram never issues).
        await self.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS student_resources_one_primary_idx
            ON student_resources (COALESCE(student_id, -1))
            WHERE is_primary = TRUE;
            """,
            execute=True,
        )

    async def migrate_student_resources(self):
        try:
            await self.create_table_student_resources()
            await self._backfill_student_resources_from_teacher_info()
        except Exception as exc:
            self._log_migration_failure("migrate_student_resources", exc)
            return

    async def _backfill_student_resources_from_teacher_info(self):
        from data.config import load_teacher_info
        from utils.resource_provider import detect_provider

        existing = await self.execute(
            "SELECT 1 FROM student_resources WHERE student_id IS NULL LIMIT 1",
            fetchval=True,
        )
        if existing:
            return

        info = load_teacher_info() or {}
        contacts = info.get("contacts", {}) if isinstance(info, dict) else {}
        candidates = []
        for key, default_label in (
            ("materials_url", "Учебные материалы"),
            ("filen_url", "Filen"),
        ):
            url = contacts.get(key) or info.get(key)
            if not url:
                continue
            candidates.append((default_label, str(url).strip()))

        seen_urls = set()
        primary_assigned = False
        for label, url in candidates:
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            provider = detect_provider(url)
            await self.execute(
                """
                INSERT INTO student_resources (student_id, label, url, provider, is_primary, sort_order)
                VALUES (NULL, $1, $2, $3, $4, 0)
                """,
                label,
                url,
                provider,
                not primary_assigned,
                execute=True,
            )
            primary_assigned = True

    async def migrate_default_pricing_rate(self):
        try:
            existing = await self.execute(
                """
                SELECT 1
                FROM lesson_pricing_rates
                WHERE group_size = 1 AND duration_minutes = 90
                """,
                fetchval=True,
            )
            if existing:
                return

            import re

            from data.config import load_teacher_info

            rate_text = str(load_teacher_info().get("requisites", {}).get("rate") or "")
            amount_match = re.search(r"(\d[\d\s]*)", rate_text)
            if not amount_match:
                return
            amount = float(amount_match.group(1).replace(" ", ""))
            duration_match = re.search(r"/\s*(\d{2,3})", rate_text)
            duration = int(duration_match.group(1)) if duration_match else 90
            await self.execute(
                """
                INSERT INTO lesson_pricing_rates (group_size, duration_minutes, amount, currency)
                VALUES (1, $1, $2, 'RUB')
                ON CONFLICT (group_size, duration_minutes) DO NOTHING
                """,
                duration,
                amount,
                execute=True,
            )
        except Exception as exc:
            self._log_migration_failure("migrate_default_pricing_rate", exc)
            return

    async def verify_required_schema(self):
        required_columns = {
            "users": {
                "language",
                "level",
                "age",
                "review_sent",
                "lesson_reminders",
                "is_internal_account",
                "lesson_format",
                "speech_style",
                "lesson_duration_minutes",
                "current_bookmark_text",
                "current_bookmark_state",
                "current_bookmark_updated_at",
                "current_bookmark_lesson_id",
                "first_lesson_invite_sent",
                "first_lesson_invite_sent_at",
                "goal_text",
                "goal_set_at",
                "onboarding_completed_at",
            },
            "lessons": {
                "lesson_date",
                "reminder_sent",
                "balance_consumed",
                "homework_check_reminder_sent",
                "source",
                "teacher_followup_sent",
                "teacher_pre_lesson_note_sent",
                "teacher_comment",
                "teacher_comment_saved_at",
            },
            "homework": {
                "reminder_sent",
                "attachment_file_id",
                "attachment_file_unique_id",
                "attachment_name",
                "attachment_mime_type",
                "materials_parsed_at",
            },
            "homework_delivery_queue": {
                "homework_id",
                "student_id",
                "delivery_kind",
                "deliver_after",
                "include_attachment",
                "last_attempt_at",
                "attempts",
                "last_error",
                "created_at",
            },
            "student_groups": {
                "group_type",
                "title",
                "primary_student_id",
                "balance_mode",
                "homework_mode",
                "onboarding_source",
                "is_active",
                "created_at",
            },
            "student_group_members": {
                "group_id",
                "student_id",
                "member_name",
                "member_role",
                "has_bot_access",
                "invite_token",
                "invite_created_at",
                "invite_used_at",
                "created_at",
            },
            "homework_material_mentions": {
                "homework_id",
                "student_id",
                "material_key",
                "material_title",
                "material_kind",
                "page_from",
                "page_to",
                "unit_label",
                "chapter_label",
                "lesson_label",
                "exercise_label",
                "raw_fragment",
                "created_at",
            },
            "blocked_telegram_ids": {
                "telegram_id",
                "reason",
                "blocked_by",
                "blocked_at",
                "previous_is_active",
            },
            "student_learning_plans": {
                "student_id",
                "status",
                "summary",
                "parsed_text",
                "parser_status",
                "parser_warnings",
                "file_id",
                "file_unique_id",
                "file_name",
                "mime_type",
                "created_by",
                "published_at",
                "archived_at",
                "created_at",
            },
            "study_plan_checklist_items": {
                "student_id",
                "lesson_id",
                "title",
                "source",
                "status",
                "sort_order",
                "completed_at",
                "created_at",
            },
            "lesson_pricing_rates": {
                "group_size",
                "duration_minutes",
                "amount",
                "currency",
                "is_active",
                "created_at",
                "updated_at",
            },
            "admin_inbox": {
                "id",
                "kind",
                "payload",
                "created_at",
                "read_at",
                "handled_at",
                "handled_by",
            },
            "student_resources": {
                "id",
                "student_id",
                "label",
                "url",
                "provider",
                "is_primary",
                "sort_order",
                "created_at",
                "created_by",
            },
            "user_journey_events": {
                "id",
                "user_id",
                "kind",
                "scheduled_at",
                "sent_at",
                "dismissed_at",
                "payload",
                "created_at",
            },
        }

        rows = await self.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_name = ANY($1::text[])
            """,
            list(required_columns.keys()),
            fetch=True,
        )
        present = {}
        for row in rows:
            present.setdefault(row["table_name"], set()).add(row["column_name"])

        missing = []
        for table_name, columns in required_columns.items():
            absent = sorted(columns - present.get(table_name, set()))
            if absent:
                missing.append(f"{table_name}: {', '.join(absent)}")

        if missing:
            raise RuntimeError(
                "Database schema is incomplete. Missing columns: " + " | ".join(missing)
            )

    async def create_all_tables(self):
        await self.create_table_users()
        await self.create_table_student_parent()
        await self.create_table_student_groups()
        await self.create_table_blocked_telegram_ids()
        await self.create_table_lessons()
        await self.create_table_payments()
        await self.create_table_homework()
        await self.create_table_homework_delivery_queue()
        await self.create_table_homework_material_mentions()
        await self.create_table_learning_plans()
        await self.create_table_lesson_pricing_rates()
        await self.create_table_calendar_student_links()
        await self.migrate_lessons_google_event_id()
        await self.migrate_lessons_add_date()
        await self.migrate_lessons_google_event_id_unique()
        await self.migrate_lessons_add_reminder_sent()
        await self.migrate_users_add_language_level()
        await self.migrate_users_add_lesson_format()
        await self.migrate_users_add_speech_style()
        await self.migrate_users_add_lesson_followup_fields()
        await self.migrate_internal_test_accounts()
        await self.migrate_lessons_add_balance_consumed()
        await self.migrate_lessons_add_homework_check_flag()
        await self.migrate_lessons_add_source()
        await self.migrate_lessons_add_teacher_followup_fields()
        await self.migrate_homework_add_material_fields()
        await self.migrate_homework_add_attachment_fields()
        await self.migrate_homework_material_mentions_indexes()
        await self.migrate_calendar_links_indexes()
        await self.migrate_student_group_member_invites()
        await self.migrate_learning_plan_schema()
        await self.migrate_users_add_first_lesson_invite()
        await self.migrate_default_pricing_rate()
        await self.migrate_admin_inbox()
        await self.migrate_student_resources()
        await self.migrate_users_add_onboarding()
        await self.migrate_user_journey_events()
        await self.verify_required_schema()
