from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from decimal import Decimal
from typing import Optional

import httpx

from bot.config import settings

BASE = "https://bpay.binanceapi.com"


def _sign(payload: str) -> tuple[str, str, str]:
    ts = str(int(time.time() * 1000))
    nonce = secrets.token_hex(16)
    raw = ts + "\n" + nonce + "\n" + payload + "\n"
    sig = hmac.new(settings.binance_pay_secret.encode(), raw.encode(), hashlib.sha512).hexdigest().upper()
    return ts, nonce, sig


async def query_order(merchant_trade_no: str | None = None, prepay_id: str | None = None) -> dict:
    """Query a Binance Pay order. Returns dict from `data` on success, else raises."""
    body: dict = {}
    if merchant_trade_no:
        body["merchantTradeNo"] = merchant_trade_no
    if prepay_id:
        body["prepayId"] = prepay_id
    payload = json.dumps(body, separators=(",", ":"))
    ts, nonce, sig = _sign(payload)
    headers = {
        "content-type": "application/json",
        "BinancePay-Timestamp": ts,
        "BinancePay-Nonce": nonce,
        "BinancePay-Certificate-SN": settings.binance_pay_key,
        "BinancePay-Signature": sig,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{BASE}/binancepay/openapi/v2/order/query", content=payload, headers=headers)
        r.raise_for_status()
        return r.json()


async def verify_order_id(order_id: str) -> Optional[Decimal]:
    """Return paid amount (USDT, truncated to 3 decimals) if PAID, else None."""
    if not settings.binance_pay_key or not settings.binance_pay_secret:
        return None
    try:
        data = await query_order(merchant_trade_no=order_id)
    except Exception:
        try:
            data = await query_order(prepay_id=order_id)
        except Exception:
            return None
    if data.get("status") != "SUCCESS":
        return None
    info = data.get("data") or {}
    if (info.get("status") or "").upper() != "PAID":
        return None
    currency = (info.get("currency") or "").upper()
    if currency not in ("USDT", "BUSD"):
        return None
    amount_raw = Decimal(str(info.get("orderAmount") or info.get("totalFee") or "0"))
    # truncate to 3 decimals per bot policy
    truncated = amount_raw.quantize(Decimal("0.001"), rounding="ROUND_DOWN")
    return truncated
