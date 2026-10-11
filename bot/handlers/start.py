from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.i18n import t
from bot.keyboards import main_menu
from bot.services import get_or_create_user
from bot.ui import edit_or_send
from bot.utils import fmt_usdt

router = Router()


def menu_text(user) -> str:
    lang = user.language
    return (
        f"{t(lang, 'welcome')}\n\n"
        f"{t(lang, 'quick_guide')}\n\n"
        f"{t(lang, 'balance_line', balance=fmt_usdt(user.balance))}"
    )


@router.message(CommandStart(deep_link=True))
async def start_deep(message: Message, command: CommandObject) -> None:
    args = command.args or ""
    ref_code = args[4:] if args.startswith("ref_") else None
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        referrer_code=ref_code,
    )
    if args.startswith("p_") and args[2:].isdigit():
        # deep link from a restock/sale post: open the product directly
        from bot.handlers.product import send_product

        await send_product(message, user, int(args[2:]))
        return
    await message.answer(menu_text(user), reply_markup=main_menu(user.language), parse_mode="Markdown")


@router.message(CommandStart())
async def start_cmd(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    await message.answer(menu_text(user), reply_markup=main_menu(user.language), parse_mode="Markdown")


@router.callback_query(F.data == "menu")
async def menu_cb(cb: CallbackQuery) -> None:
    user = await get_or_create_user(
        cb.from_user.id, cb.from_user.username, cb.from_user.full_name
    )
    await edit_or_send(cb, menu_text(user), main_menu(user.language), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()
