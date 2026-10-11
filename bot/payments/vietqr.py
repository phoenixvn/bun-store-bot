"""VietQR bank-transfer top-up, auto-confirmed by SePay (https://docs.sepay.vn).

Flow:
  1. User picks an amount in VND. ``create_session`` stores a PENDING Deposit with
     ``method="vietqr"`` and ``external_id`` = a memo code (``BMxxxxxxxx``) the user must
     put in the transfer content, and sends a VietQR image that pre-fills it.
  2. SePay POSTs every incoming transfer to /sepay/webhook (or ``poll_loop`` pulls
     them via the SePay API). ``handle_transfer`` finds the memo in the content.

Money rules:
  - The memo row is only a LOOKUP for which user paid. A QR can be paid twice, so the
    idempotency key is SePay's transaction id, never the memo: the first transfer
    approves the memo row (tx id recorded in ``raw``), later ones go through
    ``record_and_credit(external_id="sepay:<tx>")``.
  - Credit what was RECEIVED (``transferAmount``), converted at the rate quoted when
    the QR was created.
  - A transfer carrying a BM… code that matches no session is reported to the admin,
    never credited. Transfers without any BM… code are unrelated and ignored.
"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
import string
from decimal import Decimal
from urllib.parse import quote

import httpx
from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, DepositStatus
from bot.payments.common import _post_credit, record_and_credit

log = logging.getLogger(__name__)

METHOD = "vietqr"
MEMO_RE = re.compile(r"BM[A-Z0-9]{8}")
_ALPHABET = string.ascii_uppercase + string.digits
_reported_unmatched: set[str] = set()


def enabled() -> bool:
    return bool(settings.bank_code and settings.bank_account)


def auto_confirm() -> bool:
    return bool(settings.sepay_webhook_key or settings.sepay_api_token)


def new_memo() -> str:
    return "BM" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def qr_url(vnd: int, memo: str) -> str:
    return (
        f"https://img.vietqr.io/image/{quote(settings.bank_code)}-{quote(settings.bank_account)}"
        f"-compact2.png?amount={int(vnd)}&addInfo={quote(memo)}"
        f"&accountName={quote(settings.bank_account_name or '')}"
    )


def vnd_to_usdt(vnd: int | Decimal, rate: float | Decimal) -> Decimal:
    rate = Decimal(str(rate))
    if rate <= 0:
        raise ValueError("VND_PER_USDT must be > 0")
    return (Decimal(vnd) / rate).quantize(Decimal("0.0001"))


async def create_session(user_id: int, vnd: int) -> tuple[int, str, Decimal]:
    """Register a pending top-up. Returns (deposit_id, memo, usdt_quote)."""
    rate = float(settings.vnd_per_usdt)
    usdt = vnd_to_usdt(vnd, rate)
    async with session_scope() as s:
        for _ in range(5):
            memo = new_memo()
            if not await s.scalar(
                select(Deposit.id).where(Deposit.method == METHOD, Deposit.external_id == memo)
            ):
                break
        dep = Deposit(
            user_id=user_id,
            method=METHOD,
            amount=usdt,
            status=DepositStatus.PENDING.value,
            external_id=memo,
            raw={"vnd": int(vnd), "rate": rate},
        )
        s.add(dep)
        await s.flush()
        return dep.id, memo, usdt


async def handle_transfer(tx_id: str, vnd: int, content: str, transfer_type: str = "in") -> str:
    """Process one bank transaction. Returns a short status for logs/tests:
    ignored | unmatched | duplicate | credited | credited_extra."""
    if transfer_type != "in" or vnd <= 0:
        return "ignored"
    m = MEMO_RE.search((content or "").upper())
    if not m:
        # the account may receive unrelated transfers — not ours to report
        return "ignored"
    memo = m.group(0)
    raw_tx = {"sepay_tx": str(tx_id), "vnd_received": int(vnd), "content": (content or "")[:300]}

    async with session_scope() as s:
        stmt = select(Deposit).where(Deposit.method == METHOD, Deposit.external_id == memo)
        if s.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        dep = await s.scalar(stmt)
        if dep is None:
            first = None
        else:
            raw = dict(dep.raw or {})
            rate = raw.get("rate") or settings.vnd_per_usdt
            usdt = vnd_to_usdt(vnd, rate)
            user_id, dep_id = dep.user_id, dep.id
            if dep.status == DepositStatus.PENDING.value:
                dep.status = DepositStatus.APPROVED.value
                dep.amount = usdt
                dep.raw = {**raw, **raw_tx}
                first = True
            elif raw.get("sepay_tx") == str(tx_id):
                return "duplicate"
            elif not raw.get("sepay_tx"):
                # approved by an admin before SePay saw it — this IS that payment:
                # record the tx so a later transfer on the same QR still credits, don't pay twice
                dep.raw = {**raw, **raw_tx}
                return "duplicate"
            else:
                first = False
    if first is None:
        await _report_unmatched(tx_id, vnd, content)
        return "unmatched"
    if first:
        await _post_credit(user_id, dep_id, METHOD, usdt)
        return "credited"
    # same QR paid again (or webhook + poller racing on a later transfer): dedupe on tx id
    credited, _ = await record_and_credit(user_id, METHOD, f"sepay:{tx_id}", usdt, raw={**raw_tx, "memo": memo})
    return "credited_extra" if credited else "duplicate"


async def _report_unmatched(tx_id: str, vnd: int, content: str) -> None:
    key = str(tx_id)
    if key in _reported_unmatched:
        return
    _reported_unmatched.add(key)
    from bot.bot_instance import notify_admin

    await notify_admin(
        f"⚠️ Bank transfer without a valid top-up code — NOT credited.\n"
        f"Amount: {int(vnd):,} VND | SePay tx: {tx_id}\nContent: {content or '—'}\n"
        f"Find the user and credit manually if needed.",
        parse_mode=None,
    )


async def poll_loop() -> None:
    """Fallback when the webhook can't reach us: pull recent transactions from SePay."""
    if not (enabled() and settings.sepay_api_token):
        return
    url = "https://my.sepay.vn/userapi/transactions/list"
    while True:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(
                    url,
                    params={"account_number": settings.bank_account, "limit": 50},
                    headers={"Authorization": f"Bearer {settings.sepay_api_token}"},
                )
            for tx in (r.json().get("transactions") or []):
                amount_in = int(float(tx.get("amount_in") or 0))
                if amount_in > 0:
                    await handle_transfer(
                        str(tx.get("id")), amount_in, tx.get("transaction_content") or "", "in"
                    )
        except Exception as e:
            log.warning("sepay poll failed: %s", e)
        await asyncio.sleep(max(20, settings.deposit_poll_interval or 30))
