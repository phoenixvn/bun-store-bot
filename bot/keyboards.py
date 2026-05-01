from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from bot.config import settings
from bot.i18n import LANGS, t
from bot.utils import fmt_usdt


def main_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "shop"), callback_data="shop:0:all")],
        [
            InlineKeyboardButton(text=t(lang, "deposit"), callback_data="dep:menu"),
            InlineKeyboardButton(text=t(lang, "profile"), callback_data="profile"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "support"), callback_data="support"),
            InlineKeyboardButton(text=t(lang, "shopee"), url="https://shopee.vn"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "earn"), callback_data="earn"),
            InlineKeyboardButton(text=t(lang, "channel"), url=settings.channel_url or "https://t.me"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_btn(lang: str, cb: str = "menu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(lang, "back"), callback_data=cb)


def deposit_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "binance_pay"), callback_data="dep:binance")],
        [InlineKeyboardButton(text=t(lang, "usdt_bep20"), callback_data="dep:bep20")],
        [
            InlineKeyboardButton(text=t(lang, "ton"), callback_data="dep:ton"),
            InlineKeyboardButton(text=t(lang, "tron"), callback_data="dep:tron"),
        ],
        [InlineKeyboardButton(text=t(lang, "other"), callback_data="dep:other")],
        [back_btn(lang)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb(lang: str, cb: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "cancel"), callback_data=cb)]]
    )


def language_kb(lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    items = list(LANGS.items())
    for i in range(0, len(items), 2):
        chunk = items[i : i + 2]
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"lang:{code}") for code, label in chunk]
        )
    rows.append([back_btn(lang, "profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_kb(lang: str, products: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in products:
        if p.unlimited:
            stock_str = "∞"
        else:
            stock_str = str(p.in_stock)
        label = f"{p.emoji} {p.name} - {fmt_usdt(p.price)} USDT (Kho: {stock_str})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"prod:{p.id}")])
    rows.append(
        [
            InlineKeyboardButton(text=t(lang, "refresh"), callback_data=f"shop:{page}:all"),
            InlineKeyboardButton(text=t(lang, "filter_all"), callback_data=f"shop:{page}:all"),
        ]
    )
    nav: list[InlineKeyboardButton] = []
    nav.append(
        InlineKeyboardButton(
            text=t(lang, "page", cur=page + 1, total=max(1, total_pages)),
            callback_data="noop",
        )
    )
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text=t(lang, "next"), callback_data=f"shop:{page+1}:all"))
    if page > 0:
        nav.insert(0, InlineKeyboardButton(text=t(lang, "prev"), callback_data=f"shop:{page-1}:all"))
    rows.append(nav)
    rows.append([back_btn(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def numpad(lang: str, product_id: int, qty: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(text=t(lang, "set_qty", qty=qty), callback_data=f"buy:{product_id}"),
            InlineKeyboardButton(text=t(lang, "del"), callback_data=f"qty:{product_id}:del"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text=str(d), callback_data=f"qty:{product_id}:{d}")
            for d in (1, 2, 3, 4, 5)
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text=str(d), callback_data=f"qty:{product_id}:{d}")
            for d in (6, 7, 8, 9, 0)
        ]
    )
    rows.append([InlineKeyboardButton(text=t(lang, "topup_wallet"), callback_data="dep:menu")])
    rows.append(
        [
            InlineKeyboardButton(text=t(lang, "share_link"), callback_data=f"share:{product_id}"),
            InlineKeyboardButton(text=t(lang, "view_note"), callback_data=f"note:{product_id}"),
        ]
    )
    rows.append([back_btn(lang, "shop:0:all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb(lang: str, notif: bool) -> InlineKeyboardMarkup:
    notif_label = t(lang, "notifications") + (" ✅" if notif else " ❌")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=notif_label, callback_data="profile:notif")],
            [
                InlineKeyboardButton(text=t(lang, "my_orders"), callback_data="orders:0"),
                InlineKeyboardButton(text=t(lang, "dev_api"), callback_data="api"),
            ],
            [InlineKeyboardButton(text=t(lang, "language"), callback_data="lang:menu")],
            [back_btn(lang)],
        ]
    )


def api_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "set_webhook"), callback_data="api:webhook")],
            [InlineKeyboardButton(text=t(lang, "revoke_api"), callback_data="api:revoke")],
            [InlineKeyboardButton(text=t(lang, "view_api_docs"), url="https://example.com/api")],
            [back_btn(lang, "profile")],
        ]
    )


def support_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=t(lang, "live_support"), callback_data="support:start")]]
    if settings.admin_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "contact_admin"),
                    url=f"https://t.me/{settings.admin_username}",
                )
            ]
        )
    rows.append([back_btn(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
