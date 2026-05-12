"""USDT deposits via Binance Spot account.

User sends USDT (BEP20 or TRC20) to merchant's Binance deposit address.
Bot polls `GET /sapi/v1/capital/deposit/hisrec` and matches credited
deposits to pending sessions by exact amount.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, DepositStatus
from bot.payments.common import record_and_credit

log = logging.getLogger(__name__)
BASE = "https://api.binance.com"


def _sign(query: str) -> str:
    return hmac.new(
        settings.binance_api_secret.encode(),
        query.encode(),
        hashlib.sha256,
    ).hexdigest()


async def _fetch_deposits(coin: str = "USDT") -> list[dict]:
    if not settings.binance_api_key or not settings.binance_api_secret:
        return []
    ts = int(time.time() * 1000)
    # last 7 days, status=1 (success/credited)
    start = ts - 7 * 24 * 60 * 60 * 1000
    params = f"coin={coin}&status=1&startTime={start}&timestamp={ts}&recvWindow=10000"
    sig = _sign(params)
    url = f"{BASE}/sapi/v1/capital/deposit/hisrec?{params}&signature={sig}"
    headers = {"X-MBX-APIKEY": settings.binance_api_key}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, headers=headers)
        if r.status_code != 200:
            log.warning("binance deposit fetch failed: %s %s", r.status_code, r.text[:200])
            return []
        return r.json() or []


async def _match_pending(amount: Decimal) -> Optional[int]:
    async with session_scope() as s:
        res = await s.execute(
            select(Deposit)
            .where(
                Deposit.method == "binance_spot",
                Deposit.status == DepositStatus.PENDING.value,
                Deposit.amount == amount,
            )
            .order_by(Deposit.id.desc())
            .limit(1)
        )
        dep = res.scalar_one_or_none()
        return dep.user_id if dep else None


async def poll_once() -> None:
    deposits = await _fetch_deposits("USDT")
    for dep in deposits:
        tx_id = dep.get("txId") or ""
        if not tx_id or tx_id.startswith("Internal transfer"):
            continue
        amount = Decimal(str(dep.get("amount") or "0")).quantize(Decimal("0.0001"))
        if amount <= 0:
            continue
        async with session_scope() as s:
            existing = await s.scalar(
                select(Deposit).where(
                    Deposit.method == "binance_spot", Deposit.external_id == tx_id
                )
            )
            if existing:
                continue
        user_id = await _match_pending(amount)
        if not user_id:
            log.info("unassigned binance_spot tx %s amount=%s", tx_id, amount)
            continue
        await record_and_credit(user_id, "binance_spot", tx_id, amount, raw=dep)


async def poll_loop() -> None:
    if not settings.binance_api_key or not settings.binance_api_secret:
        log.info("BINANCE_API_KEY not set — Binance Spot poller disabled")
        return
    while True:
        try:
            await poll_once()
        except Exception as e:  # noqa
            log.warning("binance_spot poll error: %s", e)
        await asyncio.sleep(settings.deposit_poll_interval)
