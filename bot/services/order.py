from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update

from bot.database import session_scope
from bot.models import Order, Product, StockItem, User
from bot.utils import best_discount, effective_price, is_promo_active

log = logging.getLogger(__name__)


@dataclass
class ProductView:
    id: int
    name: str
    emoji: str
    price: Decimal
    warranty: str
    description: str
    note: str
    unlimited: bool
    in_stock: int
    discount_tiers: list[dict]
    original_price: Decimal | None = None  # set if promo active
    promo_until: object = None
    max_qty: int | None = None  # per-purchase cap (supplier products)


def _visible():
    # supplier products disappear when FatCat stops listing them for us
    return Product.is_active.is_(True) & (
        Product.supplier_product_id.is_(None) | Product.supplier_available.is_(True)
    )


async def _count_stock(session, product_id: int) -> int:
    p = await session.get(Product, product_id)
    if p is not None and p.supplier_product_id is not None:
        return p.supplier_stock or 0
    return (
        await session.scalar(
            select(func.count(StockItem.id)).where(
                StockItem.product_id == product_id, StockItem.sold.is_(False)
            )
        )
    ) or 0


async def list_products(
    page: int, per_page: int = 10, emoji_filter: str | None = None
) -> tuple[list[ProductView], int]:
    async with session_scope() as s:
        base = select(Product).where(_visible())
        cnt_base = select(func.count(Product.id)).where(_visible())
        if emoji_filter:
            base = base.where(Product.emoji == emoji_filter)
            cnt_base = cnt_base.where(Product.emoji == emoji_filter)
        total = (await s.scalar(cnt_base)) or 0
        res = await s.execute(
            base.order_by(Product.id).limit(per_page).offset(page * per_page)
        )
        rows = res.scalars().all()
        views = []
        for p in rows:
            stock = await _count_stock(s, p.id)
            promo = is_promo_active(p)
            views.append(
                ProductView(
                    id=p.id,
                    name=p.name,
                    emoji=p.emoji,
                    price=effective_price(p),
                    warranty=p.warranty,
                    description=p.description,
                    note=p.note,
                    unlimited=p.unlimited,
                    in_stock=stock,
                    discount_tiers=p.discount_tiers or [],
                    original_price=Decimal(p.price) if promo else None,
                    promo_until=p.promo_until if promo else None,
                    max_qty=p.supplier_max_qty if p.supplier_product_id is not None else None,
                )
            )
        import math

        pages = max(1, math.ceil(total / per_page))
        return views, pages


async def get_product(product_id: int) -> Optional[ProductView]:
    async with session_scope() as s:
        p = await s.get(Product, product_id)
        if not p:
            return None
        stock = await _count_stock(s, p.id)
        promo = is_promo_active(p)
        return ProductView(
            id=p.id,
            name=p.name,
            emoji=p.emoji,
            price=effective_price(p),
            warranty=p.warranty,
            description=p.description,
            note=p.note,
            unlimited=p.unlimited,
            in_stock=stock,
            discount_tiers=p.discount_tiers or [],
            original_price=Decimal(p.price) if promo else None,
            promo_until=p.promo_until if promo else None,
            max_qty=p.supplier_max_qty if p.supplier_product_id is not None else None,
        )


class BuyError(Exception):
    pass


@dataclass
class BuyResult:
    order_id: int
    quantity: int
    total: Decimal
    discount_percent: Decimal
    payloads: list[str]
    product_name: str
    status: str = "completed"  # completed | partial | pending
    refunded: Decimal = Decimal("0")


async def buy_product(
    user_id: int, product_id: int, quantity: int, via_api: bool = False
) -> BuyResult:
    if quantity <= 0:
        raise BuyError("qty")
    async with session_scope() as s:
        p = await s.get(Product, product_id)
        supplier_linked = p is not None and p.supplier_product_id is not None
    if supplier_linked:
        return await _buy_from_supplier(user_id, product_id, quantity, via_api)
    async with session_scope() as s:
        p = await s.get(Product, product_id, with_for_update=True)
        if not p or not p.is_active:
            raise BuyError("no_stock")

        discount = best_discount(quantity, p.discount_tiers or [])
        unit = effective_price(p)
        total = (unit * quantity * (Decimal("100") - discount) / Decimal("100")).quantize(
            Decimal("0.0001")
        )

        u = await s.get(User, user_id, with_for_update=True)
        if not u:
            raise BuyError("no_user")
        if u.balance < total:
            raise BuyError("insufficient")

        payloads: list[str] = []
        if p.unlimited:
            # a single synthetic payload — admin must set p.description or note as template
            for _ in range(quantity):
                payloads.append(p.description or f"{p.name} — contact admin to receive")
            stock_items: list[StockItem] = []
        else:
            stmt = (
                select(StockItem)
                .where(StockItem.product_id == p.id, StockItem.sold.is_(False))
                .order_by(StockItem.id)
                .limit(quantity)
            )
            if s.bind.dialect.name != "sqlite":
                stmt = stmt.with_for_update(skip_locked=True)
            res = await s.execute(stmt)
            stock_items = list(res.scalars().all())
            if len(stock_items) < quantity:
                raise BuyError("no_stock")
            payloads = [it.payload for it in stock_items]

        u.balance -= total

        order = Order(
            user_id=user_id,
            product_id=p.id,
            product_name=p.name,
            quantity=quantity,
            unit_price=unit,
            total=total,
            discount_percent=discount,
            via_api=via_api,
        )
        s.add(order)
        await s.flush()

        for it in stock_items:
            it.sold = True
            it.order_id = order.id
            from datetime import datetime

            it.sold_at = datetime.utcnow()

        return BuyResult(
            order_id=order.id,
            quantity=quantity,
            total=total,
            discount_percent=discount,
            payloads=payloads,
            product_name=p.name,
        )


async def list_user_orders(user_id: int, page: int, per_page: int = 10):
    async with session_scope() as s:
        total = (
            await s.scalar(select(func.count(Order.id)).where(Order.user_id == user_id))
        ) or 0
        res = await s.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.id.desc())
            .limit(per_page)
            .offset(page * per_page)
        )
        rows = res.scalars().all()
        import math

        pages = max(1, math.ceil(total / per_page))
        return rows, pages


async def _buy_from_supplier(
    user_id: int, product_id: int, quantity: int, via_api: bool
) -> BuyResult:
    from bot.bot_instance import notify_admin
    from bot.services import supplier
    from bot.suppliers import fatcat

    if not fatcat.enabled():
        raise BuyError("no_stock")

    # 1. cheap checks from the synced cache (<= SUPPLIER_SYNC_INTERVAL old). Stale stock is
    #    safe: if FatCat can't fill, it answers 400 and the user is refunded.
    async with session_scope() as s:
        p = await s.get(Product, product_id)
        if not p or not p.is_active or not p.supplier_available:
            raise BuyError("no_stock")
        max_qty = p.supplier_max_qty or fatcat.HARD_MAX_QTY
        stock, unit_vnd, name = p.supplier_stock or 0, p.supplier_price_vnd or 0, p.name
        u = await s.get(User, user_id)
        user_balance = Decimal(u.balance) if u else Decimal("0")
    if quantity > max_qty:
        raise BuyError("max_qty")
    if stock < quantity or unit_vnd <= 0:
        raise BuyError("no_stock")
    need_vnd = unit_vnd * quantity
    if user_balance < supplier.cost_usdt(need_vnd):
        raise BuyError("insufficient")

    # one live call (FatCat allows 60 req/min per key): is our supplier wallet funded?
    try:
        sup_balance = await fatcat.balance_vnd()
    except fatcat.SupplierUnreachable as e:
        log.warning("supplier pre-check failed: %s", e)
        raise BuyError("supplier_down")
    except fatcat.SupplierError as e:
        await notify_admin(f"⚠️ FatCat API rejected pre-check: {e}", parse_mode=None)
        raise BuyError("supplier_down")
    if sup_balance < need_vnd:
        await notify_admin(
            f"⚠️ FatCat wallet too low: have {sup_balance:,} VND, order needs {need_vnd:,} VND "
            f"({quantity}x {name}). Top up the FatCat wallet.",
            parse_mode=None,
        )
        raise BuyError("supplier_down")

    # 2. debit + pending order, committed before calling the supplier
    async with session_scope() as s:
        p = await s.get(Product, product_id, with_for_update=True)
        discount = best_discount(quantity, p.discount_tiers or [])
        unit = effective_price(p)
        total = (unit * quantity * (Decimal("100") - discount) / Decimal("100")).quantize(
            Decimal("0.0001")
        )
        if total < supplier.cost_usdt(need_vnd):
            # manual price / promo / discount tier would sell below supplier cost
            await notify_admin(
                f"⚠️ Blocked loss-making sale of {quantity}x {p.name}: "
                f"{total} USDT < cost {supplier.cost_usdt(need_vnd)} USDT. Fix price/promo/tiers.",
                parse_mode=None,
            )
            raise BuyError("no_stock")
        u = await s.get(User, user_id, with_for_update=True)
        if not u:
            raise BuyError("no_user")
        if u.balance < total:
            raise BuyError("insufficient")
        u.balance -= total
        order = Order(
            user_id=user_id,
            product_id=p.id,
            product_name=p.name,
            quantity=quantity,
            unit_price=unit,
            total=total,
            discount_percent=discount,
            via_api=via_api,
            status="pending",
        )
        s.add(order)
        await s.flush()
        # random suffix: a DB reset must never collide with an old supplier order id
        order.request_id = f"bm{order.id}-{secrets.token_hex(4)}"
        order_id, product_name = order.id, p.name

    # 3. call the supplier (idempotent on request_id); unresolved => reconcile_loop
    out = await supplier.fulfill_with_retry(order_id)
    if out.status == "refunded":
        log.info("supplier refused order %s: %s", order_id, out.error)
        if out.supplier_status in (400, 404):
            raise BuyError("no_stock")  # sold out / delisted between sync and purchase
        await notify_admin(f"⚠️ FatCat refused order #{order_id}: {out.error}", parse_mode=None)
        raise BuyError("supplier_down")
    async with session_scope() as s:
        o = await s.get(Order, order_id)
        final_total, final_qty = Decimal(o.total), o.quantity
    return BuyResult(
        order_id=order_id,
        quantity=final_qty,
        total=final_total,
        discount_percent=discount,
        payloads=out.payloads,
        product_name=product_name,
        status=out.status,
        refunded=out.refunded,
    )
