from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.i18n import t
from bot.keyboards import shop_kb
from bot.services import get_or_create_user
from bot.services.order import list_products

router = Router()


@router.callback_query(F.data.startswith("shop:"))
async def shop(cb: CallbackQuery) -> None:
    _, page_str, _flt = cb.data.split(":", 2)
    page = int(page_str)
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    products, pages = await list_products(page)
    text = t(user.language, "products_available")
    try:
        await cb.message.edit_text(text, reply_markup=shop_kb(user.language, products, page, pages))
    except Exception:
        await cb.message.answer(text, reply_markup=shop_kb(user.language, products, page, pages))
    await cb.answer()
