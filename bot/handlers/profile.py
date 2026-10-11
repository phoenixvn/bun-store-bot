from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import T, t
from bot.keyboards import profile_kb, back_btn
from bot.services import get_or_create_user, toggle_notifications
from bot.services.order import list_user_orders
from bot.config import settings
from bot.ui import edit_or_send
from bot.utils import fmt_usdt, fmt_vnd

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
    await edit_or_send(cb, text, profile_kb(lang, user.notifications), parse_mode="Markdown")
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


ORDERS_PER_PAGE = 5

STATUS_ICON = {"completed": "✅", "partial": "🟡", "pending": "⏳", "refunded": "↩️"}


@router.callback_query(F.data.startswith("orders:"))
async def orders(cb: CallbackQuery) -> None:
    page = int(cb.data.split(":")[1])
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    rows, pages = await list_user_orders(user.id, page, per_page=ORDERS_PER_PAGE)
    text = t(lang, "orders_hint") if rows else t(lang, "no_orders")
    kb_rows: list[list[InlineKeyboardButton]] = []
    for o in rows:
        code = f"#{o.code}" if o.code else f"#{o.id}"
        label = f"{STATUS_ICON.get(o.status, '•')} {code} • {o.product_name[:30]} x{o.quantity}"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"order:{o.id}")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=t(lang, "prev"), callback_data=f"orders:{page-1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(text=t(lang, "page", cur=page + 1, total=pages), callback_data="noop"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text=t(lang, "next"), callback_data=f"orders:{page+1}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([back_btn(lang)])
    await edit_or_send(cb, text, InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await cb.answer()


@router.callback_query(F.data == "wallet")
async def wallet(cb: CallbackQuery) -> None:
    from bot.keyboards import wallet_kb

    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    text = t(lang, "wallet_card", balance=fmt_usdt(user.balance))
    if settings.bank_account and settings.vnd_per_usdt:
        text += "\n" + t(lang, "wallet_vnd_hint", rate=fmt_vnd(settings.vnd_per_usdt))
    await edit_or_send(cb, text, wallet_kb(lang), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data.startswith("deposits:"))
async def deposits_history(cb: CallbackQuery) -> None:
    from bot.database import session_scope
    from bot.models import Deposit
    from sqlalchemy import func, select
    from bot.utils import fmt_usdt

    page = int(cb.data.split(":")[1])
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    per_page = 10
    async with session_scope() as s:
        total = await s.scalar(
            select(func.count(Deposit.id)).where(Deposit.user_id == user.id)
        ) or 0
        rows = (
            await s.execute(
                select(Deposit)
                .where(Deposit.user_id == user.id)
                .order_by(Deposit.id.desc())
                .limit(per_page)
                .offset(page * per_page)
            )
        ).scalars().all()
    import math
    pages = max(1, math.ceil(total / per_page))
    icon = {"approved": "✅", "pending": "⏳", "rejected": "❌"}
    lines = ["💸 *Deposit history*\n"]
    if not rows:
        lines.append("_No deposits yet._")
    for d in rows:
        lines.append(
            f"{icon.get(d.status, '•')} `{d.method}` {fmt_usdt(d.amount)} USDT — {d.created_at.strftime('%m-%d %H:%M')}"
        )
    kb_rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=t(lang, "prev"), callback_data=f"deposits:{page-1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text=t(lang, "next"), callback_data=f"deposits:{page+1}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([back_btn(lang, "profile")])
    try:
        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
            parse_mode="Markdown",
        )
    except Exception:
        await cb.message.answer(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
            parse_mode="Markdown",
        )
    await cb.answer()


@router.callback_query(F.data.startswith("order:"))
async def order_detail(cb: CallbackQuery) -> None:
    from bot.database import session_scope
    from bot.models import Order, StockItem
    from sqlalchemy import select
    from bot.utils import fmt_usdt

    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    order_id = int(cb.data.split(":")[1])
    async with session_scope() as s:
        o = await s.get(Order, order_id)
        if not o or o.user_id != user.id:
            await cb.answer("❌", show_alert=True)
            return
        items = (
            await s.execute(select(StockItem).where(StockItem.order_id == order_id))
        ).scalars().all()
        payloads = [it.payload for it in items]
    from html import escape

    code = f"#{o.code}" if o.code else f"#{o.id}"
    lines = [
        f"🧾 <b>{t(lang, 'order_label')} {code}</b>",
        f"📦 {escape(o.product_name)} x{o.quantity}",
        f"💰 {t(lang, 'total')}: {fmt_usdt(o.total)} USDT",
        f"📅 {o.created_at.strftime('%Y-%m-%d %H:%M')}",
        f"{STATUS_ICON.get(o.status, '•')} {t(lang, 'status_' + o.status)}",
    ]
    if payloads:
        lines.append("")
        lines.extend(f"<code>{escape(p)}</code>" for p in payloads)
    lines += ["", t(lang, "order_support_hint")]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "support"), callback_data="support")],
            [InlineKeyboardButton(text=t(lang, "back"), callback_data="orders:0")],
        ]
    )
    await edit_or_send(cb, "\n".join(lines), kb, parse_mode="HTML")
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
