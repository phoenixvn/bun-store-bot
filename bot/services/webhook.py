from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import httpx

from bot.config import settings
from bot.database import session_scope
from bot.models import ApiKey, User

log = logging.getLogger(__name__)


async def notify_balance_change(user_id: int, delta: Decimal, reason: str) -> None:
    async with session_scope() as s:
        u = await s.get(User, user_id)
        if not u:
            return
        ak = await s.get(ApiKey, user_id)
        if not ak or not ak.webhook_url or not ak.active:
            return
        body = {
            "user_id": user_id,
            "balance": str(u.balance),
            "delta": str(delta),
            "reason": reason,
        }
        payload = json.dumps(body).encode()
        sig = hmac.new(settings.webhook_hmac_secret.encode(), payload, hashlib.sha256).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(
                    ak.webhook_url,
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Signature": sig,
                        "X-API-Key": ak.key,
                    },
                )
        except Exception as e:  # noqa
            log.warning("webhook post failed for %s: %s", user_id, e)
