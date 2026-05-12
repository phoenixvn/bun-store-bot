from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select

from bot.database import session_scope
from bot.models import ApiKey, Deposit, Order, ReferralEarning, StockItem, User
from bot.utils import gen_api_key, gen_ref_code


async def get_or_create_user(
    tg_id: int,
    username: Optional[str],
    full_name: Optional[str],
    referrer_code: Optional[str] = None,
) -> User:
    async with session_scope() as s:
        u = await s.get(User, tg_id)
        if u:
            changed = False
            if username and u.username != username:
                u.username = username
                changed = True
            if full_name and u.full_name != full_name:
                u.full_name = full_name
                changed = True
            if changed:
                await s.flush()
            return u
        # new user
        ref = None
        if referrer_code:
            res = await s.execute(select(User).where(User.ref_code == referrer_code))
            r = res.scalar_one_or_none()
            if r and r.id != tg_id:
                ref = r.id
        u = User(
            id=tg_id,
            username=username,
            full_name=full_name,
            ref_code=gen_ref_code(),
            referrer_id=ref,
        )
        s.add(u)
        await s.flush()
        # create api key
        ak = ApiKey(user_id=u.id, key=gen_api_key())
        s.add(ak)
        new_user_id = u.id
        new_user_name = u.full_name or "—"
        new_user_handle = u.username or "—"
        new_user_ref = ref
    # Admin notification (outside session_scope to avoid blocking commit)
    from bot.bot_instance import bot, notify_admin

    ref_note = f" (ref by `{new_user_ref}`)" if new_user_ref else ""
    await notify_admin(
        f"👋 *NEW USER* {new_user_name} (@{new_user_handle}) `{new_user_id}`{ref_note}"
    )
    # DM referrer that they got a new referral
    if new_user_ref and bot:
        try:
            await bot.send_message(
                new_user_ref,
                f"🎉 *New referral!*\n\n"
                f"{new_user_name} (@{new_user_handle}) just joined via your link.\n"
                f"You'll earn 1% on every deposit they make (max $1 per deposit).",
                parse_mode="Markdown",
            )
        except Exception:
            pass
    async with session_scope() as s:
        return await s.get(User, new_user_id)


async def set_language(tg_id: int, lang: str) -> None:
    async with session_scope() as s:
        u = await s.get(User, tg_id)
        if u:
            u.language = lang


async def toggle_notifications(tg_id: int) -> bool:
    async with session_scope() as s:
        u = await s.get(User, tg_id)
        if not u:
            return False
        u.notifications = not u.notifications
        return u.notifications


async def credit_balance(tg_id: int, amount: Decimal) -> Decimal:
    async with session_scope() as s:
        u = await s.get(User, tg_id, with_for_update=True)
        if not u:
            raise ValueError("user not found")
        u.balance = (u.balance or Decimal("0")) + amount
        return u.balance


async def debit_balance(tg_id: int, amount: Decimal) -> bool:
    async with session_scope() as s:
        u = await s.get(User, tg_id, with_for_update=True)
        if not u or u.balance < amount:
            return False
        u.balance -= amount
        return True


async def referral_stats(tg_id: int) -> dict:
    async with session_scope() as s:
        now = datetime.utcnow()
        d1 = now - timedelta(days=1)
        d7 = now - timedelta(days=7)

        total_refs = (
            await s.scalar(select(func.count(User.id)).where(User.referrer_id == tg_id))
        ) or 0
        refs_24h = (
            await s.scalar(
                select(func.count(User.id)).where(
                    User.referrer_id == tg_id, User.created_at >= d1
                )
            )
        ) or 0
        refs_7d = (
            await s.scalar(
                select(func.count(User.id)).where(
                    User.referrer_id == tg_id, User.created_at >= d7
                )
            )
        ) or 0

        earned = await s.scalar(
            select(func.coalesce(func.sum(ReferralEarning.amount), 0)).where(
                ReferralEarning.referrer_id == tg_id
            )
        )
        avail = await s.scalar(
            select(func.coalesce(func.sum(ReferralEarning.amount), 0)).where(
                ReferralEarning.referrer_id == tg_id,
                ReferralEarning.transferred.is_(False),
                ReferralEarning.withdrawn.is_(False),
            )
        )
        transferred = await s.scalar(
            select(func.coalesce(func.sum(ReferralEarning.amount), 0)).where(
                ReferralEarning.referrer_id == tg_id, ReferralEarning.transferred.is_(True)
            )
        )
        withdrawn = await s.scalar(
            select(func.coalesce(func.sum(ReferralEarning.amount), 0)).where(
                ReferralEarning.referrer_id == tg_id, ReferralEarning.withdrawn.is_(True)
            )
        )

        return {
            "d1": refs_24h,
            "d7": refs_7d,
            "total": total_refs,
            "earned": Decimal(earned or 0),
            "avail": Decimal(avail or 0),
            "transferred": Decimal(transferred or 0),
            "withdrawn": Decimal(withdrawn or 0),
        }
