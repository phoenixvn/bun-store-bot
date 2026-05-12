from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update

from bot.database import session_scope
from bot.models import Order, Product, StockItem, User
from bot.utils import best_discount, effective_price, is_promo_active


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


async def _count_stock(session, product_id: int) -> int:
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
        base = select(Product).where(Product.is_active.is_(True))
        cnt_base = select(func.count(Product.id)).where(Product.is_active.is_(True))
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


async def buy_product(
    user_id: int, product_id: int, quantity: int, via_api: bool = False
) -> BuyResult:
    if quantity <= 0:
        raise BuyError("qty")
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
