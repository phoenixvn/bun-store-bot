from __future__ import annotations

from decimal import Decimal

import json as _json

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from bot.admin_web import router as admin_router
from bot.database import session_scope
from bot.models import ApiKey, Order, User
from bot.services.order import BuyError, buy_product

app = FastAPI(title="Bami Store Developer API", version="1.0")
app.include_router(admin_router)


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
                "code": o.code,
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
        raise HTTPException(503 if str(e) == "supplier_down" else 400, str(e))
    async with session_scope() as s:
        ak = await s.get(ApiKey, user_id)
        if ak:
            ak.api_orders += 1
            ak.api_spend = (ak.api_spend or Decimal("0")) + Decimal(result.total)
    return {
        "order_id": result.order_id,
        "code": result.code,
        "quantity": result.quantity,
        "total": str(result.total),
        "discount_percent": str(result.discount_percent),
        "payloads": result.payloads,
        # pending: items still arriving from the supplier — poll /v1/orders/{order_id}
        "status": result.status,
        "refunded": str(result.refunded),
    }


@app.get("/v1/orders/{order_id}")
async def order_detail(order_id: int, user_id: int = Depends(auth)):
    from bot.models import StockItem

    async with session_scope() as s:
        o = await s.get(Order, order_id)
        if not o or o.user_id != user_id:
            raise HTTPException(404, "order not found")
        items = (
            await s.execute(
                select(StockItem.payload).where(StockItem.order_id == order_id).order_by(StockItem.id)
            )
        ).scalars().all()
    return {
        "id": o.id,
        "code": o.code,
        "product": o.product_name,
        "quantity": o.quantity,
        "total": str(o.total),
        "status": o.status,
        "payloads": list(items),
        "created_at": o.created_at.isoformat(),
    }


@app.get("/")
async def root():
    return {"name": "Bami Store API", "endpoints": ["/v1/balance", "/v1/orders", "/v1/orders/{id}", "/v1/buy"]}


@app.post("/cryptomus/webhook")
async def cryptomus_webhook(request: Request):
    from bot.payments import cryptomus

    raw = await request.body()
    try:
        data = _json.loads(raw)
    except Exception:
        raise HTTPException(400, "bad json")
    if not isinstance(data, dict) or not cryptomus.verify_sign(data):
        raise HTTPException(403, "bad sign")
    try:
        await cryptomus.handle_webhook(data)
    except Exception:
        # acknowledge anyway — the poller will retry; Cryptomus retries on non-200
        pass
    return {"status": "ok"}


@app.post("/sepay/webhook")
async def sepay_webhook(request: Request, authorization: str = Header("")):
    """SePay bank-transfer notification (VietQR top-ups). Auth: `Authorization: Apikey <key>`."""
    import hmac

    from bot.config import settings
    from bot.payments import vietqr

    if not settings.sepay_webhook_key:
        raise HTTPException(503, "SePay webhook not configured")
    if not hmac.compare_digest(authorization.strip(), f"Apikey {settings.sepay_webhook_key}"):
        raise HTTPException(401, "bad api key")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "bad json")
    if not isinstance(data, dict) or data.get("id") is None:
        raise HTTPException(400, "missing id")
    status = await vietqr.handle_transfer(
        str(data["id"]),
        int(float(data.get("transferAmount") or 0)),
        str(data.get("content") or data.get("description") or ""),
        str(data.get("transferType") or ""),
    )
    return {"success": True, "status": status}


@app.get("/healthz")
async def healthz():
    from sqlalchemy import text as sql_text

    from bot.bot_instance import bot

    db_ok = False
    try:
        async with session_scope() as s:
            await s.execute(sql_text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    bot_ok = bot is not None
    if db_ok and bot_ok:
        return {"status": "ok", "db": True, "bot": True}
    raise HTTPException(503, f"unhealthy db={db_ok} bot={bot_ok}")
