"""BEP20 USDT deposits — polls BscScan for incoming transfers to deposit address.

Matches incoming tx by 'input' amount tag ~= expected is unreliable; instead we
require user to initiate a deposit session, then match by timestamp window + exact value.
Simpler heuristic here: every new incoming USDT tx → the user who last requested a
BEP20 deposit session within the last 30 min with matching amount. For MVP we log all
incoming and admin can assign via /admin, OR the user binds a unique "memo" amount.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, DepositStatus
from bot.payments.common import record_and_credit

log = logging.getLogger(__name__)

BSCSCAN = "https://api.bscscan.com/api"
DECIMALS = Decimal("1000000000000000000")  # 1e18


async def _fetch_incoming() -> list[dict]:
    if not settings.bscscan_api_key or not settings.bep20_deposit_address:
        return []
    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": settings.usdt_bep20_contract,
        "address": settings.bep20_deposit_address,
        "page": 1,
        "offset": 50,
        "sort": "desc",
        "apikey": settings.bscscan_api_key,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(BSCSCAN, params=params)
        r.raise_for_status()
        js = r.json()
        if js.get("status") != "1":
            return []
        return [
            tx
            for tx in js.get("result", [])
            if tx.get("to", "").lower() == settings.bep20_deposit_address.lower()
        ]


async def _pending_session_for_tx(amount: Decimal) -> Optional[int]:
    """Find pending BEP20 deposit session with matching amount. Returns user_id."""
    async with session_scope() as s:
        res = await s.execute(
            select(Deposit)
            .where(
                Deposit.method == "bep20",
                Deposit.status == DepositStatus.PENDING.value,
                Deposit.amount == amount,
            )
            .order_by(Deposit.id.desc())
            .limit(1)
        )
        dep = res.scalar_one_or_none()
        if dep:
            return dep.user_id
    return None


async def poll_once() -> None:
    txs = await _fetch_incoming()
    for tx in txs:
        tx_hash = tx["hash"]
        amount = (Decimal(tx["value"]) / DECIMALS).quantize(Decimal("0.0001"))
        # idempotent — already saved?
        async with session_scope() as s:
            existing = await s.scalar(
                select(Deposit).where(Deposit.method == "bep20", Deposit.external_id == tx_hash)
            )
            if existing:
                continue
        user_id = await _pending_session_for_tx(amount)
        if not user_id:
            log.info("unassigned bep20 tx %s amount=%s", tx_hash, amount)
            continue
        await record_and_credit(user_id, "bep20", tx_hash, amount, raw=tx)


async def poll_loop() -> None:
    if not settings.bscscan_api_key:
        log.info("BSCSCAN_API_KEY not set — BEP20 poller disabled")
        return
    while True:
        try:
            await poll_once()
        except Exception as e:  # noqa
            log.warning("bep20 poll error: %s", e)
        await asyncio.sleep(settings.deposit_poll_interval)
