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
        await self.create_table_blocked_telegram_ids()
        await self.create_table_lessons()
        await self.create_table_payments()
        await self.create_table_homework()
        await self.create_table_homework_material_mentions()
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
        await self.verify_required_schema()
