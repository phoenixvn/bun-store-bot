"""FatCat supplier glue: product sync, order fulfillment, pending-order reconciliation.

Money rules (see https://api.fatcatstore.click/docs, "Chống mua trùng"):
- The user's balance is debited and the Order row (status=pending, request_id set) is
  committed BEFORE /api/buy is called, so a crash mid-call leaves a recoverable row.
- SupplierError (definitive 4xx) => supplier did not charge => refund the user.
- SupplierUnreachable (timeout/5xx/429) => outcome unknown => keep pending and retry with
  the SAME request_id; never refund and never create a fresh supplier order.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_UP, Decimal

from sqlalchemy import delete, select

from bot.config import settings
from bot.database import session_scope
from bot.models import Order, Product, StockItem, User
from bot.suppliers import fatcat
from bot.suppliers.fatcat import SupplierError, SupplierProduct, SupplierUnreachable

log = logging.getLogger(__name__)

ALERT_AFTER_ATTEMPTS = 40  # ~20 min of failed retries at 30s

_inflight: set[int] = set()  # order ids currently being fulfilled (single replica)


# ---------------------------------------------------------------- pricing

def cost_usdt(price_vnd: int) -> Decimal:
    rate = Decimal(str(settings.vnd_per_usdt or 0))
    if rate <= 0:
        raise ValueError("VND_PER_USDT must be > 0")
    return (Decimal(price_vnd) / rate).quantize(Decimal("0.0001"), rounding=ROUND_UP)


def sell_usdt(price_vnd: int) -> Decimal:
    markup = Decimal(str(settings.supplier_markup_percent or 0))
    raw = cost_usdt(price_vnd) * (Decimal("100") + markup) / Decimal("100")
    return max(Decimal("0.01"), raw.quantize(Decimal("0.01"), rounding=ROUND_UP))


def _apply_supplier_fields(p: Product, sp: SupplierProduct) -> bool:
    """Copy live supplier data onto a product row. Returns True if sell price changed."""
    p.supplier_product_id = sp.id
    p.supplier_price_vnd = sp.max_unit_vnd
    p.supplier_stock = sp.stock
    p.supplier_max_qty = max(1, min(sp.max_quantity, fatcat.HARD_MAX_QTY))
    p.supplier_available = True
    p.unlimited = False
    p.cost_price = cost_usdt(sp.max_unit_vnd)
    if p.supplier_auto_price:
        new_price = sell_usdt(sp.max_unit_vnd)
        if p.price is None or Decimal(p.price) != new_price:
            p.price = new_price
            return True
    return False


# ---------------------------------------------------------------- sync

@dataclass
class SyncResult:
    seen: int = 0
    created: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    repriced: int = 0
    events: list["StockEvent"] = field(default_factory=list)


@dataclass
class StockEvent:
    """Something customers want to hear about. Sent after the sync commits."""
    kind: str  # new | restock | sale
    product_id: int
    added: int = 0
    stock: int = 0
    old_vnd: int = 0
    new_vnd: int = 0


RESTOCK_MIN_ADD = 5  # FatCat stock oscillates by 1-2 as it pulls from source; ignore that noise
SALE_MIN_DROP = 0.05  # >= 5% cheaper at the supplier


def _detect_event(p: Product, old_stock: int, old_vnd: int | None, is_new: bool) -> StockEvent | None:
    """Compare pre-sync values with what _apply_supplier_fields just wrote.
    Uses supplier VND, never the USDT sell price, so editing VND_PER_USDT can't fire SALE."""
    if not p.is_active or not p.supplier_available:
        return None
    now = datetime.now(timezone.utc)
    last = p.last_notified_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    cooldown = timedelta(minutes=max(1, settings.restock_cooldown_min or 180))
    if last is not None and now - last < cooldown:
        return None
    new_stock, new_vnd = p.supplier_stock or 0, p.supplier_price_vnd or 0
    ev = None
    if is_new and new_stock > 0:
        ev = StockEvent("new", 0, added=new_stock, stock=new_stock)
    elif old_vnd and new_vnd and new_vnd <= old_vnd * (1 - SALE_MIN_DROP) and new_stock > 0:
        ev = StockEvent("sale", p.id, stock=new_stock, old_vnd=old_vnd, new_vnd=new_vnd)
    elif new_stock > 0 and (old_stock == 0 or new_stock - old_stock >= RESTOCK_MIN_ADD):
        ev = StockEvent("restock", p.id, added=new_stock - old_stock, stock=new_stock)
    if ev is not None:
        p.last_notified_at = now
    return ev


# keyword -> category emoji from keyboards.CATEGORIES, so new items show under shop filters
_EMOJI_HINTS = [
    (("gpt", "gemini", "claude", "grok", "perplexity", "copilot", "cursor", " ai"), "✨"),
    (("capcut", "canva", "adobe", "figma", "picsart"), "🎨"),
    (("netflix", "youtube", "spotify", "disney", "prime video", "hbo"), "🎧"),
    (("duolingo", "coursera", "udemy", "elsa", "quizlet"), "📚"),
    (("drive", "onedrive", "dropbox", "icloud", "storage"), "📦"),
    (("office", "microsoft", "notion", "zoom", "slack", "teams"), "🎯"),
    (("vpn", "nord", "express", "surfshark", "kaspersky"), "🛡"),
]


def _guess_emoji(name: str) -> str:
    n = f" {name.lower()}"
    for keys, emoji in _EMOJI_HINTS:
        if any(k in n for k in keys):
            return emoji
    return "🔧"


async def sync_products(detect_events: bool = True) -> SyncResult:
    remote = await fatcat.products()
    res = SyncResult(seen=len(remote))
    by_id = {sp.id: sp for sp in remote}
    async with session_scope() as s:
        rows = (await s.execute(select(Product))).scalars().all()
        linked = {p.supplier_product_id: p for p in rows if p.supplier_product_id is not None}
        unlinked_by_name = {
            (p.name or "").strip().lower(): p for p in rows if p.supplier_product_id is None
        }
        pending_new: list[tuple[Product, StockEvent]] = []
        for sp in remote:
            p = linked.get(sp.id)
            is_new = False
            if p is None:
                # admin may have hand-imported this product earlier — link instead of duplicating
                p = unlinked_by_name.pop(sp.name.strip().lower(), None)
                if p is not None:
                    res.linked.append(sp.name)
                else:
                    p = Product(
                        name=sp.name[:128],
                        emoji=_guess_emoji(sp.name),
                        description=sp.description,
                        warranty="See description",
                        is_active=bool(settings.supplier_auto_activate),
                        supplier_auto_price=True,
                        discount_tiers=[],
                    )
                    s.add(p)
                    res.created.append(sp.name)
                    is_new = True
            old_stock, old_vnd = (p.supplier_stock or 0), p.supplier_price_vnd
            if _apply_supplier_fields(p, sp):
                res.repriced += 1
            ev = _detect_event(p, old_stock, old_vnd, is_new) if detect_events else None
            if ev is not None:
                if is_new:
                    pending_new.append((p, ev))
                else:
                    res.events.append(ev)
        for spid, p in linked.items():
            if spid not in by_id and p.supplier_available:
                p.supplier_available = False
                p.supplier_stock = 0
                res.removed.append(p.name)
        if pending_new:
            await s.flush()  # new products need ids for their "Buy now" button
            for p, ev in pending_new:
                ev.product_id = p.id
                res.events.append(ev)
    return res


async def notify_stock_events(events: list[StockEvent]) -> int:
    """DM opted-in users about restocks/sales with a Buy-now button. Throttled to stay
    under Telegram's ~30 msg/s bot limit. Returns messages sent."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from bot.bot_instance import bot
    from bot.i18n import t
    from bot.utils import fmt_usdt

    if not events or not bot or not settings.restock_notify:
        return 0
    async with session_scope() as s:
        users = (
            await s.execute(select(User.id, User.language).where(User.notifications.is_(True)))
        ).all()
        prods = {p.id: p for p in (await s.execute(
            select(Product).where(Product.id.in_([e.product_id for e in events]))
        )).scalars().all()}
    sent = 0
    for ev in events:
        p = prods.get(ev.product_id)
        if p is None:
            continue
        for uid, lang in users:
            if ev.kind == "sale":
                text = t(
                    lang, "notify_sale", name=p.name, old=fmt_usdt(sell_usdt(ev.old_vnd)),
                    new=fmt_usdt(p.price), stock=ev.stock,
                )
            else:
                key = "notify_new" if ev.kind == "new" else "notify_restock"
                text = t(lang, key, name=p.name, added=ev.added, stock=ev.stock, price=fmt_usdt(p.price))
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "buy_now"), callback_data=f"prod:{p.id}", style="success")
            ]])
            try:
                await bot.send_message(uid, text, reply_markup=kb)
                sent += 1
            except Exception as e:
                # blocked the bot / deleted account — skip quietly
                log.debug("stock notify to %s failed: %s", uid, e)
            await asyncio.sleep(0.05)
    log.info("stock notify: %d events, %d messages", len(events), sent)
    return sent


async def sync_loop() -> None:
    if not fatcat.enabled():
        log.info("supplier sync disabled (SUPPLIER_API_KEY empty)")
        return
    first = True
    while True:
        try:
            r = await sync_products(detect_events=not first)
            if first or r.created or r.removed or r.linked:
                log.info(
                    "supplier sync: %d listed, +%d new, %d linked, -%d removed, %d repriced",
                    r.seen, len(r.created), len(r.linked), len(r.removed), r.repriced,
                )
            if not first and (r.created or r.removed):
                from bot.bot_instance import notify_admin

                lines = ["🐱 *FatCat catalog changed*"]
                lines += [f"➕ {n}" for n in r.created]
                lines += [f"➖ {n}" for n in r.removed]
                await notify_admin("\n".join(lines), parse_mode=None)
            # the very first sync after boot only builds the baseline
            if not first and r.events:
                asyncio.create_task(notify_stock_events(r.events))
            first = False
        except Exception as e:
            log.warning("supplier sync failed: %s", e)
        await asyncio.sleep(max(15, settings.supplier_sync_interval or 60))


# ---------------------------------------------------------------- fulfillment

@dataclass
class FulfillOutcome:
    status: str  # completed | partial | pending | refunded
    payloads: list[str]
    refunded: Decimal = Decimal("0")
    error: str = ""
    supplier_status: int = 0  # HTTP status of a definitive SupplierError


async def _refund(s, o: Order, amount: Decimal) -> None:
    if amount <= 0:
        return
    u = await s.get(User, o.user_id, with_for_update=True)
    if u:
        u.balance = Decimal(u.balance) + amount
    o.total = Decimal(o.total) - amount


async def _payloads(s, order_id: int) -> list[str]:
    rows = (
        await s.execute(
            select(StockItem).where(StockItem.order_id == order_id).order_by(StockItem.id)
        )
    ).scalars().all()
    return [r.payload for r in rows]


async def fulfill(order_id: int) -> FulfillOutcome:
    """One idempotent /api/buy attempt for a pending order, then persist the result."""
    if order_id in _inflight:
        async with session_scope() as s:
            return FulfillOutcome("pending", await _payloads(s, order_id))
    _inflight.add(order_id)
    try:
        async with session_scope() as s:
            o = await s.get(Order, order_id)
            if o is None:
                raise ValueError(f"order {order_id} not found")
            if o.status != "pending":
                return FulfillOutcome(o.status, await _payloads(s, order_id))
            p = await s.get(Product, o.product_id)
            spid = p.supplier_product_id if p else None
            qty, request_id = o.quantity, o.request_id

        err: Exception | None = None
        sorder = None
        if spid is None or not request_id:
            err = SupplierError(404, "product no longer linked to supplier")
        else:
            try:
                sorder = await fatcat.buy(spid, qty, request_id)
            except (SupplierError, SupplierUnreachable) as e:
                err = e

        async with session_scope() as s:
            o = await s.get(Order, order_id, with_for_update=True)
            if o.status != "pending":
                return FulfillOutcome(o.status, await _payloads(s, order_id))
            o.supplier_attempts = (o.supplier_attempts or 0) + 1

            if isinstance(err, SupplierUnreachable):
                o.supplier_error = str(err)[:500]
                return FulfillOutcome("pending", await _payloads(s, order_id), error=str(err))

            if isinstance(err, SupplierError):
                # definitive: supplier did not charge us => give the user their money back
                amount = Decimal(o.total)
                await _refund(s, o, amount)
                o.status = "refunded"
                o.supplier_error = str(err)[:500]
                return FulfillOutcome(
                    "refunded", [], refunded=amount, error=str(err), supplier_status=err.status
                )

            assert sorder is not None
            o.supplier_order_id = sorder.id or o.supplier_order_id
            o.supplier_error = None
            # a replay returns the order's full item list, possibly in a different order —
            # treat the longest response as authoritative instead of appending by index
            have = await _payloads(s, order_id)
            payloads = have
            if len(sorder.items) >= len(have):
                payloads = list(sorder.items)
                await s.execute(delete(StockItem).where(StockItem.order_id == o.id))
                now = datetime.utcnow()
                for item in payloads:
                    s.add(
                        StockItem(
                            product_id=o.product_id, payload=item, sold=True, sold_at=now, order_id=o.id
                        )
                    )
            delivered = len(payloads)

            if sorder.fulfillment == "pending" and delivered < o.quantity:
                return FulfillOutcome("pending", payloads)

            refunded = Decimal("0")
            if delivered < o.quantity:
                # partial: supplier refunded the missing units to us; pass that on pro-rata
                refunded = (Decimal(o.total) * (o.quantity - delivered) / o.quantity).quantize(
                    Decimal("0.0001")
                )
                await _refund(s, o, refunded)
                o.quantity = delivered
            if delivered == 0:
                o.status = "refunded"
            else:
                o.status = "partial" if refunded > 0 else "completed"
            return FulfillOutcome(o.status, payloads, refunded=refunded)
    finally:
        _inflight.discard(order_id)


async def fulfill_with_retry(order_id: int, attempts: int = 3) -> FulfillOutcome:
    out = await fulfill(order_id)
    for i in range(1, attempts):
        if out.status != "pending":
            break
        await asyncio.sleep(1.5 * i)
        out = await fulfill(order_id)
    return out


# ---------------------------------------------------------------- reconcile

async def _deliver_late(order_id: int, out: FulfillOutcome) -> None:
    """DM the user once a pending order resolves in the background."""
    from bot.bot_instance import bot
    from bot.i18n import t
    from bot.services.webhook import notify_balance_change
    from bot.utils import fmt_usdt

    async with session_scope() as s:
        o = await s.get(Order, order_id)
        u = await s.get(User, o.user_id)
    lang = u.language if u else "en"
    if out.refunded > 0:
        await notify_balance_change(o.user_id, out.refunded, f"refund:{order_id}")
    if not bot:
        return
    from bot.handlers.product import buy_result_text
    from bot.services.order import BuyResult

    if out.status == "refunded":
        text = t(lang, "supplier_order_refunded", id=o.code or order_id, amount=fmt_usdt(out.refunded))
    else:
        text = buy_result_text(
            lang,
            BuyResult(
                order_id=o.id,
                quantity=len(out.payloads),
                total=Decimal(o.total),
                discount_percent=Decimal(o.discount_percent or 0),
                payloads=out.payloads,
                product_name=o.product_name,
                status=out.status,
                refunded=out.refunded,
                code=o.code or "",
            ),
        )
    try:
        await bot.send_message(o.user_id, text, parse_mode="HTML")
    except Exception as e:
        log.warning("late delivery DM to %s failed: %s", o.user_id, e)


async def reconcile_once() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=20)
    async with session_scope() as s:
        ids = (
            await s.execute(
                select(Order.id)
                .where(
                    Order.status == "pending",
                    Order.request_id.is_not(None),
                    Order.created_at < cutoff,
                )
                .order_by(Order.id)
                .limit(50)
            )
        ).scalars().all()
    resolved = 0
    for oid in ids:
        if oid in _inflight:
            continue
        try:
            out = await fulfill(oid)
        except Exception as e:
            log.warning("reconcile order %s failed: %s", oid, e)
            continue
        if out.status != "pending":
            resolved += 1
            await _deliver_late(oid, out)
            continue
        async with session_scope() as s:
            o = await s.get(Order, oid)
            attempts = o.supplier_attempts if o else 0
        if attempts == ALERT_AFTER_ATTEMPTS:
            from bot.bot_instance import notify_admin

            await notify_admin(
                f"⚠️ FatCat order #{oid} still pending after {attempts} attempts "
                f"(request_id {o.request_id}). Last error: {o.supplier_error or '—'}. "
                f"User was charged; check /admin/supplier.",
                parse_mode=None,
            )
    return resolved


async def reconcile_loop() -> None:
    if not fatcat.enabled():
        return
    while True:
        try:
            await reconcile_once()
        except Exception as e:
            log.warning("supplier reconcile failed: %s", e)
        await asyncio.sleep(30)
