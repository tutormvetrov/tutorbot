import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from keyboards.inline import back_to_menu_keyboard
from handlers.users.screens import get_profile_payload, get_user_home_payload
from utils.db_api.postgresql import Database
from utils.ui_text import build_help_text

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("menu"))
async def command_menu(message: Message, db: Database):
    logger.info(f"Команда /menu от {message.from_user.id}")
    text, keyboard = await get_user_home_payload(db, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def command_help(message: Message):
    logger.info(f"Команда /help от {message.from_user.id}")
    await message.answer(build_help_text())


@router.message(Command("profile"))
async def command_profile(message: Message, db: Database):
    logger.info(f"Команда /profile от {message.from_user.id}")
    text, keyboard = await get_profile_payload(db, message.from_user.id)
    await message.answer(text, reply_markup=keyboard or back_to_menu_keyboard)
