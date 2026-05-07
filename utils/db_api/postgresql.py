import asyncpg
from asyncpg.pool import Pool

from data import config
from utils.db_api.admin_inbox import DatabaseAdminInboxMixin
from utils.db_api.admin_today import DatabaseAdminTodayMixin
from utils.db_api.balance_transactions import DatabaseBalanceTransactionsMixin
from utils.db_api.calendar_links import DatabaseCalendarLinksMixin
from utils.db_api.finance import DatabaseFinanceMixin
from utils.db_api.homework import DatabaseHomeworkMixin
from utils.db_api.journey import DatabaseJourneyMixin
from utils.db_api.lessons import DatabaseLessonMixin
from utils.db_api.payments import DatabasePaymentMixin
from utils.db_api.progress import DatabaseProgressMixin
from utils.db_api.pulse import DatabasePulseMixin
from utils.db_api.schema import DatabaseSchemaMixin
from utils.db_api.student_resources import DatabaseStudentResourcesMixin
from utils.db_api.study_plans import DatabaseStudyPlanMixin
from utils.db_api.users import DatabaseUserMixin
from utils.db_api.work_rules import DatabaseWorkRulesMixin


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
    DatabasePulseMixin,
    DatabaseProgressMixin,
    DatabaseBalanceTransactionsMixin,
    DatabaseFinanceMixin,
    DatabaseWorkRulesMixin,
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
