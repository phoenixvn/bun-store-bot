from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.i18n import t
from bot.keyboards import main_menu
from bot.services import get_or_create_user
from bot.utils import fmt_usdt

router = Router()


async def _send_menu(message: Message, user) -> None:
    lang = user.language
    text = f"{t(lang, 'welcome')}\n\n💳 {t(lang, 'balance_line', balance=fmt_usdt(user.balance))}"
    await message.answer(text, reply_markup=main_menu(lang))


@router.message(CommandStart(deep_link=True))
async def start_deep(message: Message, command: CommandObject) -> None:
    ref_code = None
    if command.args and command.args.startswith("ref_"):
        ref_code = command.args[4:]
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        referrer_code=ref_code,
    )
    await _send_menu(message, user)


@router.message(CommandStart())
async def start_cmd(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    await _send_menu(message, user)


@router.callback_query(F.data == "menu")
async def menu_cb(cb: CallbackQuery) -> None:
    user = await get_or_create_user(
        cb.from_user.id, cb.from_user.username, cb.from_user.full_name
    )
    lang = user.language
    text = f"{t(lang, 'welcome')}\n\n💳 {t(lang, 'balance_line', balance=fmt_usdt(user.balance))}"
    try:
        await cb.message.edit_text(text, reply_markup=main_menu(lang))
    except Exception:
        await cb.message.answer(text, reply_markup=main_menu(lang))
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()
