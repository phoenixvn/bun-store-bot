"""Binance Pay (personal P2P) deposits.

Polls /sapi/v1/pay/transactions on the merchant's Binance Spot account
and matches incoming Binance Pay transfers to pending deposit sessions
by exact amount.

Use this when Binance Pay merchant API is unavailable in your region —
this consumer-side endpoint works with a normal Spot API key (Reading only).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from decimal import Decimal

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


async def _fetch_transactions() -> list[dict]:
    if not settings.binance_api_key or not settings.binance_api_secret:
        return []
    ts = int(time.time() * 1000)
    start = ts - 7 * 24 * 60 * 60 * 1000  # last 7 days
    qs = f"startTime={start}&timestamp={ts}&recvWindow=10000"
    sig = _sign(qs)
    url = f"{BASE}/sapi/v1/pay/transactions?{qs}&signature={sig}"
    headers = {"X-MBX-APIKEY": settings.binance_api_key}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, headers=headers)
        if r.status_code != 200:
            log.warning(
                "binance pay fetch failed: %s %s", r.status_code, r.text[:200]
            )
            return []
        body = r.json()
        if not body.get("success"):
            log.warning("binance pay non-success: %s", body)
            return []
        return body.get("data") or []


async def _match_pending(amount: Decimal):
    async with session_scope() as s:
        res = await s.execute(
            select(Deposit)
            .where(
                Deposit.method == "binance_pay",
                Deposit.status == DepositStatus.PENDING.value,
                Deposit.amount == amount,
            )
            .order_by(Deposit.id.desc())
            .limit(1)
        )
        dep = res.scalar_one_or_none()
        return dep.user_id if dep else None


async def poll_once() -> None:
    txs = await _fetch_transactions()
    for tx in txs:
        if (tx.get("currency") or "").upper() != "USDT":
            continue
        if tx.get("orderType") != "PAY":
            continue
        try:
            amount = Decimal(str(tx.get("amount") or "0"))
        except Exception:
            continue
        if amount <= 0:  # negative = outgoing payment
            continue
        amount = amount.quantize(Decimal("0.0001"))
        ext_id = tx.get("transactionId") or tx.get("orderId")
        if not ext_id:
            continue
        async with session_scope() as s:
            existing = await s.scalar(
                select(Deposit).where(
                    Deposit.method == "binance_pay",
                    Deposit.external_id == ext_id,
                )
            )
            if existing:
                continue
        user_id = await _match_pending(amount)
        if not user_id:
            log.info(
                "unassigned binance_pay tx %s amount=%s", ext_id, amount
            )
            continue
        await record_and_credit(user_id, "binance_pay", ext_id, amount, raw=tx)


async def poll_loop() -> None:
    if not settings.binance_api_key or not settings.binance_api_secret:
        log.info("BINANCE_API_KEY not set — Binance Pay poller disabled")
        return
    if not settings.binance_pay_id:
        log.info("BINANCE_PAY_ID not set — Binance Pay poller disabled")
        return
    while True:
        try:
            await poll_once()
        except Exception as e:  # noqa
            log.warning("binance_pay poll error: %s", e)
        await asyncio.sleep(settings.deposit_poll_interval)
