from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, ReferralEarning, User


async def award_referral(deposit_id: int) -> tuple[int | None, Decimal]:
    """Credit referrer 1% of deposit (capped). Returns (referrer_tg_id, amount)."""
    async with session_scope() as s:
        dep = await s.get(Deposit, deposit_id)
        if not dep:
            return None, Decimal("0")
        u = await s.get(User, dep.user_id)
        if not u or not u.referrer_id:
            return None, Decimal("0")

        existing = await s.scalar(
            select(ReferralEarning).where(ReferralEarning.deposit_id == deposit_id)
        )
        if existing:
            return None, Decimal("0")

        amount = (Decimal(dep.amount) * Decimal(str(settings.referral_rate))).quantize(
            Decimal("0.0001")
        )
        cap = Decimal(str(settings.referral_max_per_deposit))
        if amount > cap:
            amount = cap
        if amount <= 0:
            return None, Decimal("0")

        referrer = await s.get(User, u.referrer_id, with_for_update=True)
        if not referrer:
            return None, Decimal("0")
        referrer.balance += amount

        earning = ReferralEarning(
            referrer_id=u.referrer_id,
            referee_id=u.id,
            deposit_id=deposit_id,
            amount=amount,
            transferred=True,
        )
        s.add(earning)
        return u.referrer_id, amount
