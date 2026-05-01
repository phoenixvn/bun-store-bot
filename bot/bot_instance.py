"""Singleton Bot instance accessible from services (for sending notifications).
Populated in bot.main at startup.
"""
from __future__ import annotations

from typing import Optional

from aiogram import Bot

bot: Optional[Bot] = None


def set_bot(b: Bot) -> None:
    global bot
    bot = b
