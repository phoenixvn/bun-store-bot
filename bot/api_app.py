from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from bot.database import session_scope
from bot.models import ApiKey, Order, User
from bot.services.order import BuyError, buy_product

app = FastAPI(title="Bun Store Developer API", version="1.0")


async def auth(x_api_key: str = Header(...)) -> int:
    async with session_scope() as s:
        res = await s.execute(select(ApiKey).where(ApiKey.key == x_api_key, ApiKey.active.is_(True)))
        ak = res.scalar_one_or_none()
        if not ak:
            raise HTTPException(401, "Invalid API key")
        return ak.user_id


@app.get("/v1/balance")
async def balance(user_id: int = Depends(auth)):
    async with session_scope() as s:
        u = await s.get(User, user_id)
        return {"user_id": user_id, "balance": str(u.balance if u else 0)}


@app.get("/v1/orders")
async def orders(user_id: int = Depends(auth), limit: int = 20):
    async with session_scope() as s:
        res = await s.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
        )
        rows = res.scalars().all()
        return [
            {
                "id": o.id,
                "product": o.product_name,
                "quantity": o.quantity,
                "total": str(o.total),
                "discount_percent": str(o.discount_percent),
                "status": o.status,
                "created_at": o.created_at.isoformat(),
            }
            for o in rows
        ]


class BuyBody(BaseModel):
    product_id: int
    quantity: int


@app.post("/v1/buy")
async def buy(body: BuyBody, user_id: int = Depends(auth)):
    try:
        result = await buy_product(user_id, body.product_id, body.quantity, via_api=True)
    except BuyError as e:
        raise HTTPException(400, str(e))
    async with session_scope() as s:
        ak = await s.get(ApiKey, user_id)
        if ak:
            ak.api_orders += 1
            ak.api_spend = (ak.api_spend or Decimal("0")) + Decimal(result.total)
    return {
        "order_id": result.order_id,
        "quantity": result.quantity,
        "total": str(result.total),
        "discount_percent": str(result.discount_percent),
        "payloads": result.payloads,
    }


@app.get("/")
async def root():
    return {"name": "Bun Store API", "endpoints": ["/v1/balance", "/v1/orders", "/v1/buy"]}
