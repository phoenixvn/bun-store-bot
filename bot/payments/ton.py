from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

import httpx
from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, DepositStatus
from bot.payments.common import record_and_credit

log = logging.getLogger(__name__)
TONCENTER = "https://toncenter.com/api/v2"
# USDT on TON — user pays in TON; we convert at a simple stored rate or treat 1:1 with USDT when jetton USDT.
# For simplicity we treat incoming TON native value as USDT using a fixed rate if configured.
# Production: use jetton transfers endpoint for USDT jetton.


async def _fetch_transactions(limit: int = 30):
    if not settings.ton_deposit_address:
        return []
    params = {"address": settings.ton_deposit_address, "limit": limit}
    headers = {}
    if settings.toncenter_api_key:
        headers["X-API-Key"] = settings.toncenter_api_key
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{TONCENTER}/getTransactions", params=params, headers=headers)
        r.raise_for_status()
        js = r.json()
        return js.get("result", [])


async def poll_once() -> None:
    txs = await _fetch_transactions()
    for tx in txs:
        tx_hash = tx.get("transaction_id", {}).get("hash")
        if not tx_hash:
            continue
        async with session_scope() as s:
            existing = await s.scalar(
                select(Deposit).where(Deposit.method == "ton", Deposit.external_id == tx_hash)
            )
            if existing:
                continue
        in_msg = tx.get("in_msg") or {}
        value = Decimal(in_msg.get("value", "0")) / Decimal("1000000000")  # nanoton → TON
        if value <= 0:
            continue
        # match to pending session by amount (TON units)
        async with session_scope() as s:
            res = await s.execute(
                select(Deposit)
                .where(
                    Deposit.method == "ton",
                    Deposit.status == DepositStatus.PENDING.value,
                    Deposit.amount == value,
                )
                .order_by(Deposit.id.desc())
                .limit(1)
            )
            dep = res.scalar_one_or_none()
        if not dep:
            log.info("unassigned ton tx %s value=%s", tx_hash, value)
            continue
        await record_and_credit(dep.user_id, "ton", tx_hash, value, raw=tx)


async def poll_loop() -> None:
    if not settings.ton_deposit_address:
        log.info("TON_DEPOSIT_ADDRESS not set — TON poller disabled")
        return
    while True:
        try:
            await poll_once()
        except Exception as e:  # noqa
            log.warning("ton poll error: %s", e)
        await asyncio.sleep(settings.deposit_poll_interval)
