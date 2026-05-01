from __future__ import annotations

import secrets
import string
from decimal import Decimal, ROUND_HALF_UP


def gen_ref_code(n: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def gen_api_key() -> str:
    return "bun_" + secrets.token_urlsafe(32)


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
