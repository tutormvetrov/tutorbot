"""Admin panel: download user guides for any role."""
from aiogram import Router, types

from handlers.users.admin_sections.common import is_admin
from keyboards.inline import make_admin_guides_picker_keyboard


router = Router()


@router.callback_query(lambda c: c.data == "admin:guides")
async def admin_guides_picker(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        "📥 <b>Инструкции по ролям</b>\n\n"
        "Выбери, чью инструкцию скачать. Можно посмотреть глазами любой роли — "
        "так удобнее понимать, что видит ученик или родитель.",
        reply_markup=make_admin_guides_picker_keyboard(),
    )
    await callback_query.answer()
