"""FatCat Store reseller API client (https://api.fatcatstore.click/docs).

Prices are VND integers. `buy()` is idempotent on `request_id`: re-sending the same
id returns the original order without charging again, so every retry path in the
bot re-uses the id it wrote to `orders.request_id` before the first call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from bot.config import settings

log = logging.getLogger(__name__)

HARD_MAX_QTY = 50  # per /api/buy call, regardless of product max_quantity


class SupplierError(Exception):
    """Definitive rejection (4xx except 429). The order was NOT charged — safe to refund."""

    def __init__(self, status: int, message: str, data: Optional[dict] = None):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.data = data or {}


class SupplierUnreachable(Exception):
    """Network error / timeout / 5xx / 429. Outcome UNKNOWN — never refund on this,
    retry with the same request_id instead."""


@dataclass
class SupplierProduct:
    id: int
    name: str
    price_vnd: int
    regular_price_vnd: int
    sale_qty: int
    stock: int
    max_quantity: int
    description: str

    @property
    def max_unit_vnd(self) -> int:
        # worst-case unit cost: sale slots are shared and can run out mid-purchase
        return max(self.price_vnd, self.regular_price_vnd)


@dataclass
class SupplierOrder:
    id: str
    request_id: Optional[str]
    quantity: int
    price_vnd: int
    items: list[str]
    fulfillment: str  # complete | pending | partial
    duplicate: bool = False
    refunded_vnd: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


def enabled() -> bool:
    return bool(settings.supplier_api_key and settings.supplier_api_url)


async def _request(method: str, path: str, **kw) -> tuple[int, dict]:
    url = settings.supplier_api_url.rstrip("/") + path
    headers = {"X-API-Key": settings.supplier_api_key}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as c:
            r = await c.request(method, url, headers=headers, **kw)
    except httpx.HTTPError as e:
        raise SupplierUnreachable(f"{type(e).__name__}: {e}") from e
    try:
        data = r.json()
    except Exception:
        data = {}
    if r.status_code == 429 or r.status_code >= 500:
        raise SupplierUnreachable(f"HTTP {r.status_code}: {data.get('message') or r.text[:200]}")
    if r.status_code >= 400:
        raise SupplierError(r.status_code, str(data.get("message") or r.text[:200]), data)
    return r.status_code, data


async def products() -> list[SupplierProduct]:
    _, data = await _request("GET", "/api/products")
    out = []
    for p in data.get("products") or []:
        price = int(p.get("price_vnd") or 0)
        out.append(
            SupplierProduct(
                id=int(p["id"]),
                name=str(p.get("name") or f"#{p['id']}"),
                price_vnd=price,
                regular_price_vnd=int(p.get("regular_price_vnd") or price),
                sale_qty=int(p.get("sale_qty") or 0),
                stock=int(p.get("stock") or 0),
                max_quantity=int(p.get("max_quantity") or HARD_MAX_QTY),
                description=str(p.get("description") or ""),
            )
        )
    return out


async def get_product(product_id: int) -> Optional[SupplierProduct]:
    for p in await products():
        if p.id == product_id:
            return p
    return None


async def balance_vnd() -> int:
    _, data = await _request("GET", "/api/balance")
    return int(data.get("balance_vnd") or 0)


async def buy(product_id: int, quantity: int, request_id: str) -> SupplierOrder:
    _, data = await _request(
        "POST",
        "/api/buy",
        json={"product_id": product_id, "quantity": quantity, "request_id": request_id},
    )
    o = data.get("order") or {}
    items = [str(x) for x in (o.get("items") or [])]
    return SupplierOrder(
        id=str(o.get("id") or o.get("order_group") or ""),
        request_id=o.get("request_id"),
        quantity=int(o.get("quantity") or quantity),
        price_vnd=int(o.get("price") or o.get("total_price") or 0),
        items=items,
        fulfillment=str(o.get("fulfillment") or ("complete" if len(items) >= quantity else "pending")),
        duplicate=bool(data.get("duplicate")),
        refunded_vnd=int(o.get("refunded") or 0),
        raw=data,
    )
