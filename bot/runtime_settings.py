"""Runtime-editable settings overlay.

Resolution order at runtime: DB row in `settings` table > env var > Field default.
On startup, `load()` pulls overrides from DB and mutates `bot.config.settings` in
place, so all existing `settings.foo` reads transparently pick up new values.

Only safe-to-mutate, non-secret keys are exposed (no BOT_TOKEN, no API secrets).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select

from bot.config import settings as _settings
from bot.database import session_scope
from bot.models import Setting

log = logging.getLogger(__name__)


def _as_int(v: str) -> int:
    return int(v) if v.strip() else 0


def _as_float(v: str) -> float:
    return float(v) if v.strip() else 0.0


def _as_bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


# env-var key -> (attribute on settings, caster, label, group)
EDITABLE: dict[str, tuple[str, Callable[[str], Any], str, str]] = {
    # Referral
    "REFERRAL_RATE":            ("referral_rate", _as_float, "Referral rate (0.01 = 1%)", "Referral"),
    "REFERRAL_MAX_PER_DEPOSIT": ("referral_max_per_deposit", _as_float, "Max payout per deposit (USDT)", "Referral"),
    "REFERRAL_MIN_WITHDRAW":    ("referral_min_withdraw", _as_float, "Min balance to withdraw (USDT)", "Referral"),
    # Deposits / payments
    "DEPOSIT_POLL_INTERVAL":    ("deposit_poll_interval", _as_int, "Poll interval (seconds)", "Deposit"),
    "BINANCE_PAY_ID":           ("binance_pay_id", str, "Binance Pay ID", "Deposit"),
    "BINANCE_PAY_NAME":         ("binance_pay_name", str, "Binance Pay display name", "Deposit"),
    "BINANCE_BEP20_ADDRESS":    ("binance_bep20_address", str, "Binance BEP20 deposit address", "Deposit"),
    "BINANCE_TRC20_ADDRESS":    ("binance_trc20_address", str, "Binance TRC20 deposit address", "Deposit"),
    # Channel / branding
    "CHANNEL_ID":               ("channel_id", _as_int, "Channel ID for auto-post (e.g. -100…)", "Channel"),
    "CHANNEL_URL":              ("channel_url", str, "Channel public link (https://t.me/…)", "Channel"),
    "ADMIN_USERNAME":           ("admin_username", str, "Admin Telegram username (no @)", "Channel"),
    "BOT_USERNAME":             ("bot_username", str, "Bot username (used in share links)", "Channel"),
    "DEFAULT_LANG":             ("default_lang", str, "Default UI language (vi/en/zh/...)", "Channel"),
    # Supplier (FatCat)
    "VND_PER_USDT":             ("vnd_per_usdt", _as_float, "Exchange rate: VND per 1 USDT", "Supplier"),
    "SUPPLIER_MARKUP_PERCENT":  ("supplier_markup_percent", _as_float, "Markup over supplier cost (%)", "Supplier"),
    "SUPPLIER_SYNC_INTERVAL":   ("supplier_sync_interval", _as_int, "Product sync interval (seconds)", "Supplier"),
    "SUPPLIER_AUTO_ACTIVATE":   ("supplier_auto_activate", _as_bool, "New supplier products go live (true/false)", "Supplier"),
    "RESTOCK_NOTIFY":           ("restock_notify", _as_bool, "DM users on restock/sale (true/false)", "Supplier"),
    "RESTOCK_COOLDOWN_MIN":     ("restock_cooldown_min", _as_int, "Min minutes between DMs per product", "Supplier"),
    # VietQR
    "BANK_CODE":                ("bank_code", str, "VietQR bank code (MB, VCB, TCB…)", "VietQR"),
    "BANK_ACCOUNT":             ("bank_account", str, "Bank account number", "VietQR"),
    "BANK_ACCOUNT_NAME":        ("bank_account_name", str, "Account holder name (no accents)", "VietQR"),
    "VIETQR_MIN_VND":           ("vietqr_min_vnd", _as_int, "Minimum top-up (VND)", "VietQR"),
}


async def load() -> None:
    """Apply DB-stored overrides onto the live settings object."""
    try:
        async with session_scope() as s:
            rows = (await s.execute(select(Setting))).scalars().all()
        applied = 0
        for row in rows:
            if row.key in EDITABLE:
                attr, cast, _, _ = EDITABLE[row.key]
                try:
                    setattr(_settings, attr, cast(row.value))
                    applied += 1
                except Exception as e:
                    log.warning("runtime_settings load %s failed: %s", row.key, e)
        log.info("runtime_settings: applied %d DB overrides", applied)
    except Exception as e:
        log.warning("runtime_settings.load skipped: %s", e)


async def set_value(key: str, value: str) -> None:
    if key not in EDITABLE:
        raise ValueError(f"setting '{key}' not editable")
    attr, cast, _, _ = EDITABLE[key]
    async with session_scope() as s:
        existing = await s.get(Setting, key)
        if existing:
            existing.value = value
        else:
            s.add(Setting(key=key, value=value))
    try:
        setattr(_settings, attr, cast(value))
    except Exception as e:
        log.warning("set_value %s cast failed: %s", key, e)


async def get_all() -> list[dict]:
    """Return list of {env_key, value, label, group, overridden} for UI rendering."""
    async with session_scope() as s:
        db_keys = {
            r.key for r in (await s.execute(select(Setting))).scalars().all()
        }
    out = []
    for env_key, (attr, _, label, group) in EDITABLE.items():
        out.append({
            "env_key": env_key,
            "value": getattr(_settings, attr, ""),
            "label": label,
            "group": group,
            "overridden": env_key in db_keys,
        })
    return out
