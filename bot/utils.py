from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.models import Product


def effective_price(p: "Product") -> Decimal:
    """Return promo_price if a promo is active, else regular price."""
    if p.promo_price is not None and p.promo_until is not None:
        if p.promo_until > datetime.now(timezone.utc):
            return Decimal(p.promo_price)
    return Decimal(p.price)


def is_promo_active(p: "Product") -> bool:
    return (
        p.promo_price is not None
        and p.promo_until is not None
        and p.promo_until > datetime.now(timezone.utc)
    )


def gen_ref_code(n: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def gen_order_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "DH" + "".join(secrets.choice(alphabet) for _ in range(7))


def fmt_vnd(value: Decimal | float | int) -> str:
    """50000 -> '50.000đ'"""
    return f"{int(Decimal(str(value))):,}".replace(",", ".") + "đ"


def gen_api_key() -> str:
    return "bami_" + secrets.token_urlsafe(32)


def fmt_usdt(value: Decimal | float | int, places: int = 2) -> str:
    d = Decimal(str(value)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    s = format(d, "f").rstrip("0").rstrip(".")
    return s if s else "0"


def parse_decimal(text: str) -> Decimal | None:
    try:
        v = Decimal(text.strip().replace(",", "."))
        return v if v > 0 else None
    except Exception:
        return None


def best_discount(qty: int, tiers: list[dict]) -> Decimal:
    """Return highest applicable discount percent."""
    if not tiers:
        return Decimal("0")
    best = Decimal("0")
    for tier in tiers:
        if qty >= int(tier.get("min", 0)):
            p = Decimal(str(tier.get("percent", 0)))
            if p > best:
                best = p
    return best
