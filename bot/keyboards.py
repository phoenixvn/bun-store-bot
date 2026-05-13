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
    rows: list[list[InlineKeyboardButton]] = []
    if settings.cryptomus_api_key and settings.cryptomus_merchant_id:
        rows.append(
            [InlineKeyboardButton(text=t(lang, "cryptomus"), callback_data="dep:cryptomus")]
        )
    if settings.binance_pay_id and settings.binance_api_key:
        rows.append(
            [InlineKeyboardButton(text=t(lang, "binance_pay"), callback_data="dep:binance")]
        )
    if settings.binance_api_key and settings.binance_api_secret:
        if settings.binance_bep20_address:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=t(lang, "binance_spot_bep20"),
                        callback_data="dep:bnb_spot_bep20",
                    )
                ]
            )
        if settings.binance_trc20_address:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=t(lang, "binance_spot_trc20"),
                        callback_data="dep:bnb_spot_trc20",
                    )
                ]
            )
    if settings.bep20_deposit_address:
        rows.append(
            [InlineKeyboardButton(text=t(lang, "usdt_bep20"), callback_data="dep:bep20")]
        )
    if settings.ton_deposit_address or settings.tron_deposit_address:
        ton_tron: list[InlineKeyboardButton] = []
        if settings.ton_deposit_address:
            ton_tron.append(InlineKeyboardButton(text=t(lang, "ton"), callback_data="dep:ton"))
        if settings.tron_deposit_address:
            ton_tron.append(InlineKeyboardButton(text=t(lang, "tron"), callback_data="dep:tron"))
        rows.append(ton_tron)
    rows.append([InlineKeyboardButton(text=t(lang, "other"), callback_data="dep:other")])
    rows.append([back_btn(lang)])
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


CATEGORIES = [
    ("💎", "BEST"),
    ("🐧", "IT"),
    ("✨", "AI"),
    ("🎨", "Design"),
    ("🎧", "Media"),
    ("📚", "Learn"),
    ("📦", "Drive"),
    ("🎯", "Work"),
    ("🛡", "Sec"),
    ("🔧", "Other"),
]


def shop_kb(lang: str, products: list, page: int, total_pages: int, flt: str = "all") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in products:
        stock_str = "∞" if p.unlimited else str(p.in_stock)
        if p.original_price is not None:
            label = f"🔥 {p.emoji} {p.name} - {fmt_usdt(p.price)} USDT ̶({fmt_usdt(p.original_price)}̶)"
        else:
            label = f"{p.emoji} {p.name} - {fmt_usdt(p.price)} USDT (Stock: {stock_str})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"prod:{p.id}")])
    # Category filter row(s)
    cat_chunk: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text=("✅" if flt == "all" else "") + t(lang, "filter_all"),
            callback_data="shop:0:all",
        )
    ]
    for emoji, label in CATEGORIES:
        marker = "✅" if flt == emoji else ""
        cat_chunk.append(
            InlineKeyboardButton(text=f"{marker}{emoji}{label}", callback_data=f"shop:0:{emoji}")
        )
    # split into rows of 5 buttons
    for i in range(0, len(cat_chunk), 5):
        rows.append(cat_chunk[i : i + 5])
    nav: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text=t(lang, "page", cur=page + 1, total=max(1, total_pages)),
            callback_data="noop",
        )
    ]
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text=t(lang, "next"), callback_data=f"shop:{page+1}:{flt}"))
    if page > 0:
        nav.insert(0, InlineKeyboardButton(text=t(lang, "prev"), callback_data=f"shop:{page-1}:{flt}"))
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
                InlineKeyboardButton(text=t(lang, "my_deposits"), callback_data="deposits:0"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "dev_api"), callback_data="api"),
                InlineKeyboardButton(text=t(lang, "language"), callback_data="lang:menu"),
            ],
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
