from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.i18n import t
from bot.keyboards import language_kb, main_menu
from bot.services import get_or_create_user, set_language

router = Router()


@router.callback_query(F.data == "lang:menu")
async def lang_menu(cb: CallbackQuery) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await cb.message.edit_text(t(user.language, "select_lang"), reply_markup=language_kb(user.language))
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def lang_set(cb: CallbackQuery) -> None:
    code = cb.data.split(":", 1)[1]
    if code == "menu":
        return
    await set_language(cb.from_user.id, code)
    await cb.answer(t(code, "lang_set"), show_alert=False)
    from bot.handlers.start import menu_text
    from bot.ui import edit_or_send

    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await edit_or_send(cb, menu_text(user), main_menu(code), parse_mode="Markdown")
