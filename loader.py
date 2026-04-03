from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from data import config
from utils.fsm_storage import JsonFileStorage

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = JsonFileStorage("/srv/tutorbot/data/fsm_storage.json")
dp = Dispatcher(storage=storage)
