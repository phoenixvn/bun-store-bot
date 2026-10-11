"""Single-message navigation: every screen edits the message the button lives on."""
from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def edit_or_send(
    cb: CallbackQuery,
    text: str,
    kb: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    """Edit the callback's message in place; fall back to a new message when the
    old one can't be edited (it's a photo such as a QR, too old, or identical)."""
    msg = cb.message
    if msg is not None and not msg.photo:
        try:
            await msg.edit_text(text, reply_markup=kb, parse_mode=parse_mode)
            return
        except Exception as e:
            if "message is not modified" in str(e):
                return
    if msg is not None:
        try:
            await msg.answer(text, reply_markup=kb, parse_mode=parse_mode)
        except Exception:
            # Markdown in user/supplier data can fail to parse — degrade to plain text
            await msg.answer(text, reply_markup=kb)
