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
TRONGRID = "https://api.trongrid.io"


async def _fetch_trc20():
    if not settings.tron_deposit_address:
        return []
    url = (
        f"{TRONGRID}/v1/accounts/{settings.tron_deposit_address}"
        f"/transactions/trc20?limit=50&only_to=true"
        f"&contract_address={settings.usdt_trc20_contract}"
    )
    headers = {}
    if settings.trongrid_api_key:
        headers["TRON-PRO-API-KEY"] = settings.trongrid_api_key
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, headers=headers)
        r.raise_for_status()
        return r.json().get("data", [])


async def poll_once() -> None:
    txs = await _fetch_trc20()
    for tx in txs:
        tx_hash = tx.get("transaction_id")
        if not tx_hash:
            continue
        async with session_scope() as s:
            existing = await s.scalar(
                select(Deposit).where(Deposit.method == "tron", Deposit.external_id == tx_hash)
            )
            if existing:
                continue
        value = Decimal(tx.get("value", "0")) / Decimal("1000000")  # trc20 usdt = 6 decimals
        if value <= 0:
            continue
        async with session_scope() as s:
            res = await s.execute(
                select(Deposit)
                .where(
                    Deposit.method == "tron",
                    Deposit.status == DepositStatus.PENDING.value,
                    Deposit.amount == value,
                )
                .order_by(Deposit.id.desc())
                .limit(1)
            )
            dep = res.scalar_one_or_none()
        if not dep:
            log.info("unassigned tron tx %s value=%s", tx_hash, value)
            continue
        await record_and_credit(dep.user_id, "tron", tx_hash, value, raw=tx)


async def poll_loop() -> None:
    if not settings.tron_deposit_address:
        log.info("TRON_DEPOSIT_ADDRESS not set — Tron poller disabled")
        return
    while True:
        try:
            await poll_once()
        except Exception as e:  # noqa
            log.warning("tron poll error: %s", e)
        await asyncio.sleep(settings.deposit_poll_interval)
