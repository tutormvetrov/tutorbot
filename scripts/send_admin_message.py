from __future__ import annotations

import asyncio
import sys

from aiogram import Bot

from data import config


async def main() -> int:
    if not config.BOT_TOKEN or not config.ADMIN_ID:
        return 1

    message = " ".join(sys.argv[1:]).strip() or "Бот обновился!"
    bot = Bot(token=config.BOT_TOKEN)
    try:
        await bot.send_message(config.ADMIN_ID, message)
    finally:
        await bot.session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
