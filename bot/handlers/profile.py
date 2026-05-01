from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import T, t
from bot.keyboards import profile_kb, back_btn
from bot.services import get_or_create_user, toggle_notifications
from bot.services.order import list_user_orders
from bot.utils import fmt_usdt

router = Router()


@router.callback_query(F.data == "profile")
async def profile(cb: CallbackQuery) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    text = t(
        lang,
        "profile_card",
        id=user.id,
        balance=fmt_usdt(user.balance),
        lang_code=lang.upper(),
        joined=user.created_at.strftime("%Y-%m-%d"),
    )
    await cb.message.edit_text(text, reply_markup=profile_kb(lang, user.notifications), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "profile:notif")
async def notif(cb: CallbackQuery) -> None:
    on = await toggle_notifications(cb.from_user.id)
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    text = t(
        lang,
        "profile_card",
        id=user.id,
        balance=fmt_usdt(user.balance),
        lang_code=lang.upper(),
        joined=user.created_at.strftime("%Y-%m-%d"),
    )
    await cb.message.edit_reply_markup(reply_markup=profile_kb(lang, on))
    await cb.answer("🔔 " + ("ON" if on else "OFF"))


@router.callback_query(F.data.startswith("orders:"))
async def orders(cb: CallbackQuery) -> None:
    page = int(cb.data.split(":")[1])
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    rows, pages = await list_user_orders(user.id, page)
    text = "💼 " + t(lang, "orders_title")
    kb_rows: list[list[InlineKeyboardButton]] = []
    if not rows:
        kb_rows.append([InlineKeyboardButton(text=t(lang, "no_orders"), callback_data="noop")])
    for o in rows:
        label = f"{o.product_name[:28]} x{o.quantity}"
        status = t(lang, "expired" if o.expired else "valid")
        kb_rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=f"order:{o.id}"),
                InlineKeyboardButton(text=status, callback_data="noop"),
            ]
        )
    kb_rows.append(
        [InlineKeyboardButton(text=t(lang, "page", cur=page + 1, total=pages), callback_data="noop")]
    )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=t(lang, "prev"), callback_data=f"orders:{page-1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text=t(lang, "next"), callback_data=f"orders:{page+1}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([back_btn(lang, "profile")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await cb.answer()


@router.callback_query(F.data == "earn")
async def earn(cb: CallbackQuery) -> None:
    from bot.services import referral_stats
    from bot.config import settings

    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    stats = await referral_stats(user.id)
    link = f"https://t.me/{settings.bot_username}?start=ref_{user.ref_code}"
    text = t(
        user.language,
        "earn_card",
        d1=stats["d1"],
        d7=stats["d7"],
        total=stats["total"],
        earned=fmt_usdt(stats["earned"]),
        avail=fmt_usdt(stats["avail"]),
        transferred=fmt_usdt(stats["transferred"]),
        withdrawn=fmt_usdt(stats["withdrawn"]),
        rate=int(settings.referral_rate * 100),
        max=fmt_usdt(settings.referral_max_per_deposit),
        link=link,
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user.language, "copy_link"), url=link)],
            [back_btn(user.language)],
        ]
    )
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
    await cb.answer()
