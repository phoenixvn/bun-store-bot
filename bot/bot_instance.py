"""Singleton Bot instance accessible from services (for sending notifications).
Populated in bot.main at startup.
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot

log = logging.getLogger(__name__)
bot: Optional[Bot] = None


def set_bot(b: Bot) -> None:
    global bot
    bot = b


async def notify_admin(text: str, parse_mode: str = "Markdown") -> None:
    """Post an event line to the support group. Silent on failure."""
    from bot.config import settings

    if not bot or not settings.support_group_id:
        return
    try:
        await bot.send_message(
            chat_id=settings.support_group_id, text=text, parse_mode=parse_mode
        )
    except Exception as e:  # noqa
        log.warning("notify_admin failed: %s", e)


async def notify_channel(text: str, parse_mode: str = "Markdown") -> bool:
    """Post a public announcement to the channel. Silent on failure."""
    from bot.config import settings

    if not bot or not settings.channel_id:
        return False
    try:
        await bot.send_message(
            chat_id=settings.channel_id, text=text, parse_mode=parse_mode
        )
        return True
    except Exception as e:  # noqa
        log.warning("notify_channel failed: %s", e)
        return False
