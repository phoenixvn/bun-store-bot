"""Cryptomus payment gateway integration.

Flow:
  1. User picks "Cryptomus" in the deposit menu and enters a USDT amount.
  2. ``create_invoice`` calls POST /v1/payment and we store a PENDING Deposit
     row with ``method="cryptomus"`` and ``external_id`` = our generated order_id.
  3. Cryptomus calls our webhook (POST /cryptomus/webhook in bot.api_app) on
     status change; ``verify_sign`` checks the signature and on a paid status we
     call ``payments.common.credit_pending_by_external_id``.
  4. ``poll_loop`` is a fallback: it re-checks PENDING cryptomus deposits via
     POST /v1/payment/info in case a webhook is missed.

Signing (per Cryptomus docs): sign = md5( base64( json_body ) + API_KEY ).
For webhooks the body Cryptomus sends is PHP ``json_encode`` output — no spaces,
forward slashes escaped — so we replicate that when recomputing.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, DepositStatus
from bot.payments.common import credit_pending_by_external_id

log = logging.getLogger(__name__)

API_BASE = "https://api.cryptomus.com/v1"
PAID_STATUSES = {"paid", "paid_over"}
FAIL_STATUSES = {"fail", "cancel", "system_fail", "refund_process", "refund_paid", "wrong_amount_waiting"}


def enabled() -> bool:
    return bool(settings.cryptomus_api_key and settings.cryptomus_merchant_id)


def _headers(body: str) -> dict[str, str]:
    sign = hashlib.md5(
        (base64.b64encode(body.encode()).decode() + settings.cryptomus_api_key).encode()
    ).hexdigest()
    return {
        "merchant": settings.cryptomus_merchant_id,
        "sign": sign,
        "Content-Type": "application/json",
    }


async def _post(path: str, payload: dict) -> Optional[dict]:
    body = json.dumps(payload, separators=(",", ":"))
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{API_BASE}{path}", content=body, headers=_headers(body))
        js = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("cryptomus %s request failed: %s", path, e)
        return None
    if r.status_code != 200 or js.get("state") != 0:
        log.warning("cryptomus %s -> %s %s", path, r.status_code, js)
        return None
    return js.get("result")


def new_order_id() -> str:
    return f"bm-{secrets.token_hex(12)}"


async def create_invoice(user_id: int, amount: Decimal) -> Optional[dict]:
    """Register a PENDING deposit and create a Cryptomus invoice.
    Returns the Cryptomus ``result`` dict (with ``url``, ``uuid`` …) or None."""
    if not enabled():
        return None
    order_id = new_order_id()
    async with session_scope() as s:
        dep = Deposit(
            user_id=user_id,
            method="cryptomus",
            amount=amount,
            status=DepositStatus.PENDING.value,
            external_id=order_id,
            raw={},
        )
        s.add(dep)
        await s.flush()

    payload: dict[str, Any] = {
        "amount": str(amount),
        "currency": "USDT",
        "order_id": order_id,
        "lifetime": 3600,
    }
    if settings.public_base_url:
        base = settings.public_base_url.rstrip("/")
        payload["url_callback"] = f"{base}/cryptomus/webhook"
        payload["url_return"] = f"https://t.me/{settings.bot_username}"
        payload["url_success"] = f"https://t.me/{settings.bot_username}"
    res = await _post("/payment", payload)
    if not res:
        # roll the pending row back so it can't be matched later
        async with session_scope() as s:
            dep = await s.scalar(
                select(Deposit).where(Deposit.method == "cryptomus", Deposit.external_id == order_id)
            )
            if dep and dep.status == DepositStatus.PENDING.value:
                dep.status = DepositStatus.REJECTED.value
        return None
    res["_order_id"] = order_id
    return res


# ---------------------------------------------------------------- webhook ----

def _candidate_serializations(data: dict) -> list[str]:
    """Cryptomus signs PHP ``json_encode($data)`` output. Depending on flags that
    is one of these variants — try them all (each is a deterministic function of
    the API key, so accepting any one does not weaken the check)."""
    out = []
    for ensure_ascii in (False, True):
        s = json.dumps(data, ensure_ascii=ensure_ascii, separators=(",", ":"))
        out.append(s)
        out.append(s.replace("/", "\\/"))
    return out


def verify_sign(data: dict) -> bool:
    """Verify a webhook payload's ``sign`` field against our API key."""
    import hmac as _hmac

    recv = data.get("sign")
    if not recv or not settings.cryptomus_api_key:
        return False
    rest = {k: v for k, v in data.items() if k != "sign"}
    for serialized in _candidate_serializations(rest):
        calc = hashlib.md5(
            (base64.b64encode(serialized.encode()).decode() + settings.cryptomus_api_key).encode()
        ).hexdigest()
        if _hmac.compare_digest(calc, recv):
            return True
    return False


def _credit_amount(data: dict) -> Decimal:
    """Best USDT-equivalent amount to credit from a paid webhook / info payload."""
    for key in ("payment_amount_usd", "merchant_amount", "amount", "payment_amount"):
        v = data.get(key)
        if v in (None, "", "0", 0):
            continue
        try:
            d = Decimal(str(v))
        except Exception:  # noqa: BLE001
            continue
        if d > 0:
            return d.quantize(Decimal("0.0001"))
    return Decimal("0")


async def handle_webhook(data: dict) -> bool:
    """Process a verified webhook payload. Returns True if it credited a balance."""
    order_id = data.get("order_id")
    status = (data.get("status") or "").lower()
    if not order_id:
        return False
    if status not in PAID_STATUSES:
        log.info("cryptomus webhook order=%s status=%s (ignored)", order_id, status)
        return False
    amount = _credit_amount(data)
    if amount <= 0:
        log.warning("cryptomus webhook order=%s paid but no amount: %s", order_id, data)
        return False
    credited, _ = await credit_pending_by_external_id("cryptomus", order_id, amount, raw=data)
    return credited


# ----------------------------------------------------------------- poller ----

async def _pending_orders() -> list[str]:
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Deposit.external_id)
                .where(
                    Deposit.method == "cryptomus",
                    Deposit.status == DepositStatus.PENDING.value,
                    Deposit.external_id.is_not(None),
                )
                .order_by(Deposit.id.desc())
                .limit(50)
            )
        ).scalars().all()
    return [r for r in rows if r]


async def poll_once() -> None:
    for order_id in await _pending_orders():
        res = await _post("/payment/info", {"order_id": order_id})
        if not res:
            continue
        status = (res.get("status") or "").lower()
        if status in PAID_STATUSES:
            amount = _credit_amount(res)
            if amount > 0:
                ok, _ = await credit_pending_by_external_id("cryptomus", order_id, amount, raw=res)
                if ok:
                    log.info("cryptomus poller credited order=%s amount=%s", order_id, amount)
        elif status in FAIL_STATUSES:
            async with session_scope() as s:
                dep = await s.scalar(
                    select(Deposit).where(
                        Deposit.method == "cryptomus", Deposit.external_id == order_id
                    )
                )
                if dep and dep.status == DepositStatus.PENDING.value:
                    dep.status = DepositStatus.REJECTED.value
                    dep.raw = res


async def poll_loop() -> None:
    if not enabled():
        log.info("CRYPTOMUS_API_KEY/MERCHANT_ID not set — Cryptomus poller disabled")
        return
    while True:
        try:
            await poll_once()
        except Exception as e:  # noqa: BLE001
            log.warning("cryptomus poll error: %s", e)
        await asyncio.sleep(max(20, settings.deposit_poll_interval))
