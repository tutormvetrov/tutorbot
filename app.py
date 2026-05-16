import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    Message,
    TelegramObject,
)

from data import config
from loader import bot, dp
from utils.config_validation import assert_runtime_config
from utils.db_api.postgresql import Database
from utils.observability import update_ops_status, write_runtime_event
from utils.ui_text import (
    BLOCKED_ACCOUNT_ALERT,
    BLOCKED_ACCOUNT_TEXT,
    DEACTIVATED_ACCOUNT_TEXT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        user_seconds: float,
        admin_seconds: float,
        callback_seconds: float,
        admin_id: int,
        clock: Callable[[], float] | None = None,
    ):
        self.user_seconds = float(user_seconds)
        self.admin_seconds = float(admin_seconds)
        self.callback_seconds = float(callback_seconds)
        self.admin_id = admin_id
        self.clock = clock or time.monotonic
        self._last_message: dict[int, float] = {}
        self._last_callback: dict[tuple[int, str], float] = {}

    async def _notify(self, event: TelegramObject):
        if isinstance(event, CallbackQuery) or (hasattr(event, "data") and hasattr(event, "message")):
            await event.answer("Подождите секунду.")
        elif isinstance(event, Message) or hasattr(event, "answer"):
            await event.answer("Подождите секунду.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if not user_id:
            return await handler(event, data)

        now = self.clock()
        if isinstance(event, CallbackQuery) or (hasattr(event, "data") and hasattr(event, "message")):
            key = (user_id, getattr(event, "data", "") or "")
            last = self._last_callback.get(key)
            if last is not None and now - last < self.callback_seconds:
                await self._notify(event)
                return None
            self._last_callback[key] = now
            return await handler(event, data)

        interval = self.admin_seconds if user_id == self.admin_id and self.admin_id else self.user_seconds
        last = self._last_message.get(user_id)
        if last is not None and now - last < interval:
            await self._notify(event)
            return None
        self._last_message[user_id] = now
        return await handler(event, data)


class DatabaseMiddleware(BaseMiddleware):
    """Инжектирует БД в хендлеры и блокирует деактивированных пользователей."""
    def __init__(self, db: Database):
        self.db = db

    async def _reject_blocked_user(self, event: TelegramObject, user_id: int):
        if hasattr(event, "data") and hasattr(event, "message"):
            try:
                await event.answer(BLOCKED_ACCOUNT_ALERT, show_alert=True)
            except Exception as exc:
                logger.warning("Не удалось показать alert заблокированному пользователю %s: %s", user_id, exc)
            return

        if hasattr(event, "answer"):
            try:
                await event.answer(BLOCKED_ACCOUNT_TEXT)
            except Exception as exc:
                logger.warning("Не удалось отправить текст блокировки пользователю %s: %s", user_id, exc)

    async def _reject_deactivated_user(self, event: TelegramObject, user_id: int):
        if hasattr(event, "data") and hasattr(event, "message"):
            try:
                await event.answer("Аккаунт деактивирован.", show_alert=True)
            except Exception as exc:
                logger.warning("Не удалось показать alert деактивированному пользователю %s: %s", user_id, exc)
            if event.message:
                try:
                    await event.message.answer(DEACTIVATED_ACCOUNT_TEXT)
                except Exception as exc:
                    logger.warning("Не удалось отправить текст деактивированному пользователю %s: %s", user_id, exc)
            return

        if hasattr(event, "answer"):
            await event.answer(DEACTIVATED_ACCOUNT_TEXT)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db

        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)

        if user_id and user_id != config.ADMIN_ID:
            if await self.db.is_telegram_id_blocked(user_id):
                await self._reject_blocked_user(event, user_id)
                return None

            db_user = await self.db.get_user(user_id)
            if db_user and db_user["is_active"] is False:
                await self._reject_deactivated_user(event, user_id)
                return None

        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception("Unhandled update error for %s: %s", type(event).__name__, exc)
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⚠️ Внутренняя ошибка. Попробуйте ещё раз.", show_alert=True)
                except Exception as answer_exc:
                    logger.warning("Не удалось закрыть callback после ошибки: %s", answer_exc)
            elif isinstance(event, Message):
                try:
                    await event.answer("⚠️ Внутренняя ошибка. Попробуйте ещё раз.")
                except Exception as answer_exc:
                    logger.warning("Не удалось отправить сообщение об ошибке: %s", answer_exc)
            return None

async def main():
    import handlers  # noqa: F401 — регистрация роутеров

    try:
        assert_runtime_config()
    except RuntimeError as exc:
        logger.critical("%s", exc)
        update_ops_status(status="error", scheduler="stopped", startup_error=str(exc))
        write_runtime_event("startup", "error", reason="invalid_config", details=str(exc))
        raise

    # Проверяем токен
    me = await bot.get_me()
    logger.info(f"Бот @{me.username} успешно подключён!")
    write_runtime_event("startup", "ok", bot_username=me.username)

    # Обновляем сообщение о рестарте, если оно было сохранено до перезапуска
    import json
    _pending_restart = config.PROJECT_ROOT / "data" / "pending_restart_msg.json"
    if _pending_restart.exists():
        logger.info("Найден pending_restart_msg.json — обновляю сообщение")
        try:
            _data = json.loads(_pending_restart.read_text(encoding="utf-8"))
            await bot.edit_message_text(
                chat_id=_data["chat_id"],
                message_id=_data["message_id"],
                text="✅ <b>Бот перезагружен</b>",
                parse_mode="HTML",
                reply_markup=None,
            )
            logger.info("Сообщение о рестарте обновлено")
        except Exception as _exc:
            logger.warning("Не удалось обновить сообщение о рестарте: %s", _exc)
        finally:
            _pending_restart.unlink(missing_ok=True)
    else:
        logger.info("pending_restart_msg.json не найден — обычный старт")

    # Инициализируем БД
    db = Database()
    await db.create_pool()
    await db.create_all_tables()
    await db.sync_all_parent_links()
    logger.info("База данных готова.")
    update_ops_status(status="starting", bot_username=me.username, scheduler="starting")

    # Регистрируем middleware. Rate limit стоит до бизнес-логики.
    dp.update.middleware(RateLimitMiddleware(
        config.RATE_LIMIT_USER_SECONDS,
        config.RATE_LIMIT_ADMIN_SECONDS,
        config.RATE_LIMIT_CALLBACK_SECONDS,
        config.ADMIN_ID,
    ))
    dp.update.middleware(DatabaseMiddleware(db))

    # Планировщик задач
    from utils.scheduler import setup_scheduler
    scheduler = setup_scheduler(bot, db)
    scheduler.start()
    logger.info("Планировщик запущен.")
    update_ops_status(status="running", bot_username=me.username, scheduler="running")

    # Публичные команды (минимальное меню для учеников/родителей)
    public_commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="menu",  description="Главное меню"),
        BotCommand(command="help",  description="Помощь"),
    ]
    await bot.set_my_commands(public_commands)

    # Команды администратора
    if config.ADMIN_ID:
        admin_commands = [
            BotCommand(command="start",   description="Начать работу с ботом"),
            BotCommand(command="admin",   description="Панель администратора"),
            BotCommand(command="menu",    description="Главное меню"),
            BotCommand(command="sync",    description="Синхронизация Google Calendar"),
            BotCommand(command="restart", description="Перезапуск бота"),
        ]
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=config.ADMIN_ID),
            )
        except Exception as e:
            logger.warning(f"Не удалось установить команды для ADMIN_ID: {e}")

    logger.info("Бот запущен!")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Останавливаем бота...")
        write_runtime_event("shutdown", "ok")
        update_ops_status(status="stopping", bot_username=me.username, scheduler="stopping")
        scheduler.shutdown()
        if db.pool:
            await db.pool.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
