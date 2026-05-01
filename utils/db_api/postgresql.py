import asyncpg
from asyncpg.pool import Pool

from data import config
from utils.db_api.admin_inbox import DatabaseAdminInboxMixin
from utils.db_api.admin_today import DatabaseAdminTodayMixin
from utils.db_api.calendar_links import DatabaseCalendarLinksMixin
from utils.db_api.homework import DatabaseHomeworkMixin
from utils.db_api.journey import DatabaseJourneyMixin
from utils.db_api.lessons import DatabaseLessonMixin
from utils.db_api.payments import DatabasePaymentMixin
from utils.db_api.schema import DatabaseSchemaMixin
from utils.db_api.student_resources import DatabaseStudentResourcesMixin
from utils.db_api.study_plans import DatabaseStudyPlanMixin
from utils.db_api.users import DatabaseUserMixin


class Database(
    DatabaseSchemaMixin,
    DatabaseAdminInboxMixin,
    DatabaseUserMixin,
    DatabaseHomeworkMixin,
    DatabaseStudyPlanMixin,
    DatabaseCalendarLinksMixin,
    DatabaseLessonMixin,
    DatabasePaymentMixin,
    DatabaseAdminTodayMixin,
    DatabaseStudentResourcesMixin,
    DatabaseJourneyMixin,
):
    def __init__(self):
        self.pool: Pool | None = None

    async def create_pool(self):
        self.pool = await asyncpg.create_pool(
            user=config.PGUSER,
            password=config.PGPASSWORD,
            host=config.PGHOST,
            port=int(config.PGPORT),
            database=config.DATABASE,
            server_settings={"TimeZone": config.TUTORBOT_TIMEZONE},
        )

    async def execute(
        self,
        command,
        *args,
        fetch: bool = False,
        fetchval: bool = False,
        fetchrow: bool = False,
        execute: bool = False,
    ):
        pool = self.pool
        if pool is None:
            raise RuntimeError("Database pool is not initialized.")

        async with pool.acquire() as connection:
            async with connection.transaction():
                if fetch:
                    result = await connection.fetch(command, *args)
                elif fetchval:
                    result = await connection.fetchval(command, *args)
                elif fetchrow:
                    result = await connection.fetchrow(command, *args)
                elif execute:
                    result = await connection.execute(command, *args)
                else:
                    result = None
            return result
