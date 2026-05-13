from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select

from bot.database import session_scope
from bot.models import Deposit, DepositStatus, User
from bot.services import credit_balance
from bot.services.referral import award_referral
from bot.services.webhook import notify_balance_change

log = logging.getLogger(__name__)


async def _post_credit(user_id: int, dep_id: int, method: str, amount: Decimal) -> Decimal:
    """Shared pipeline after a deposit row is APPROVED: credit balance, referral,
    developer webhook, DM user + referrer, notify admin. Returns new balance."""
    new_balance = await credit_balance(user_id, amount)
    ref_id, ref_amount = await award_referral(dep_id)
    await notify_balance_change(user_id, amount, f"deposit:{method}")

    from bot.bot_instance import bot, notify_admin

    if bot:
        try:
            await bot.send_message(
                user_id,
                f"✅ +{amount} USDT ({method})\nBalance: {new_balance} USDT",
            )
        except Exception:
            pass
        if ref_id and ref_amount > 0:
            try:
                await bot.send_message(ref_id, f"💰 +{ref_amount} USDT (referral)")
            except Exception:
                pass
    await notify_admin(
        f"💸 *DEPOSIT* +{amount} USDT via `{method}`\n"
        f"User: `{user_id}` | New balance: {new_balance} USDT"
    )
    return new_balance


async def record_and_credit(
    user_id: int,
    method: str,
    external_id: str,
    amount: Decimal,
    raw: dict | None = None,
) -> tuple[bool, Decimal]:
    """Idempotent deposit record + balance credit + referral + webhook."""
    if amount <= 0:
        return False, Decimal("0")
    async with session_scope() as s:
        existing = await s.scalar(
            select(Deposit).where(Deposit.method == method, Deposit.external_id == external_id)
        )
        if existing:
            return False, Decimal("0")
        dep = Deposit(
            user_id=user_id,
            method=method,
            amount=amount,
            status=DepositStatus.APPROVED.value,
            external_id=external_id,
            raw=raw or {},
        )
        s.add(dep)
        await s.flush()
        dep_id = dep.id

    new_balance = await _post_credit(user_id, dep_id, method, amount)
    return True, new_balance


async def credit_pending_by_external_id(
    method: str,
    external_id: str,
    amount: Decimal,
    raw: dict | None = None,
) -> tuple[bool, Decimal]:
    """Credit a deposit that was pre-registered as PENDING with this external_id
    (used by hosted-checkout gateways like Cryptomus). Idempotent: a row already
    APPROVED is left untouched. Returns (credited, new_balance)."""
    if amount <= 0:
        return False, Decimal("0")
    async with session_scope() as s:
        dep = await s.scalar(
            select(Deposit).where(Deposit.method == method, Deposit.external_id == external_id)
        )
        if not dep:
            log.warning("credit_pending_by_external_id: no pending row for %s/%s", method, external_id)
            return False, Decimal("0")
        if dep.status == DepositStatus.APPROVED.value:
            return False, Decimal("0")
        dep.status = DepositStatus.APPROVED.value
        dep.amount = amount
        dep.raw = raw or {}
        await s.flush()
        dep_id, user_id = dep.id, dep.user_id

    new_balance = await _post_credit(user_id, dep_id, method, amount)
    return True, new_balance
