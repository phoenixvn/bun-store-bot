"""Broadcast audience resolution + send execution."""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import distinct, exists, select

from bot.bot_instance import bot, notify_channel
from bot.database import session_scope
from bot.models import Broadcast, Deposit, DepositStatus, Order, User

log = logging.getLogger(__name__)

AUDIENCES = {
    "all":          "All users",
    "depositors":   "Users with at least one approved deposit",
    "buyers":       "Users with at least one order",
    "has_balance":  "Users with balance > 0",
    "by_lang":      "Users by language (param: vi|en|zh|id|es|ru|ar)",
    "ids":          "Specific user IDs (param: comma-separated)",
    "none":         "No DM (channel only)",
}


async def resolve_audience(audience: str, param: str = "") -> list[int]:
    if audience == "none":
        return []
    async with session_scope() as s:
        if audience == "all":
            res = await s.execute(select(User.id))
        elif audience == "depositors":
            res = await s.execute(
                select(distinct(User.id)).join(
                    Deposit,
                    (Deposit.user_id == User.id)
                    & (Deposit.status == DepositStatus.APPROVED.value),
                )
            )
        elif audience == "buyers":
            res = await s.execute(
                select(distinct(User.id)).join(Order, Order.user_id == User.id)
            )
        elif audience == "has_balance":
            res = await s.execute(select(User.id).where(User.balance > 0))
        elif audience == "by_lang":
            res = await s.execute(select(User.id).where(User.language == (param or "vi")))
        elif audience == "ids":
            ids = []
            for chunk in (param or "").replace("\n", ",").split(","):
                chunk = chunk.strip()
                if chunk.lstrip("-").isdigit():
                    ids.append(int(chunk))
            return ids
        else:
            return []
        return [row[0] for row in res.all()]


async def execute_broadcast(
    audience: str,
    audience_param: str,
    text: str,
    parse_mode: str,
    to_users: bool,
    to_channel: bool,
) -> dict:
    user_ids: list[int] = []
    if to_users and audience != "none":
        user_ids = await resolve_audience(audience, audience_param)

    pm = parse_mode if parse_mode and parse_mode.lower() != "plain" else None
    sent = failed = 0
    if to_users and bot:
        for uid in user_ids:
            try:
                await bot.send_message(uid, text, parse_mode=pm)
                sent += 1
            except Exception:
                failed += 1

    channel_ok = False
    if to_channel:
        channel_ok = await notify_channel(text, parse_mode=pm or "Markdown")

    async with session_scope() as s:
        bc = Broadcast(
            audience=audience,
            audience_param=audience_param or "",
            text=text,
            parse_mode=parse_mode or "Markdown",
            to_users=to_users,
            to_channel=to_channel,
            recipients=len(user_ids),
            sent=sent,
            failed=failed,
            channel_ok=channel_ok,
        )
        s.add(bc)
        await s.flush()
        bc_id = bc.id

    return {
        "id": bc_id,
        "recipients": len(user_ids),
        "sent": sent,
        "failed": failed,
        "channel_ok": channel_ok,
    }
