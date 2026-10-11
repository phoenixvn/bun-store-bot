from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.i18n import t
from bot.keyboards import shop_kb
from bot.services import get_or_create_user
from bot.services.order import list_products
from bot.ui import edit_or_send

router = Router()

PER_PAGE = 12


@router.callback_query(F.data.startswith("shop:"))
async def shop(cb: CallbackQuery) -> None:
    _, page_str, flt = cb.data.split(":", 2)
    page = int(page_str)
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    emoji_filter = None if flt == "all" else flt
    products, pages, total = await list_products(page, per_page=PER_PAGE, emoji_filter=emoji_filter)
    text = t(user.language, "products_available")
    if not products:
        text += "\n\n" + t(user.language, "no_products")
    await edit_or_send(cb, text, shop_kb(user.language, products, page, pages, flt, total))
    await cb.answer()
