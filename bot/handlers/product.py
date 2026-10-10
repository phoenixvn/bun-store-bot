from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.i18n import t
from bot.keyboards import numpad
from bot.services import get_or_create_user
from bot.services.order import BuyError, ProductView, buy_product, get_product
from bot.services.webhook import notify_balance_change
from bot.utils import best_discount, fmt_usdt

router = Router()


async def _render(cb: CallbackQuery, p: ProductView, qty: int, lang: str, balance: Decimal):
    stock_str = "∞" if p.unlimited else str(p.in_stock)
    discount = best_discount(qty, p.discount_tiers)
    unit = Decimal(p.price)
    total = (unit * qty * (Decimal("100") - discount) / Decimal("100")).quantize(Decimal("0.0001"))

    lines = [f"{p.emoji} *{t(lang,'product')}:* {p.name}"]
    if p.original_price is not None:
        from datetime import datetime, timezone
        remain = ""
        if p.promo_until:
            delta = p.promo_until - datetime.now(timezone.utc)
            secs = max(0, int(delta.total_seconds()))
            if secs >= 3600:
                remain = f" — còn {secs//3600}h {(secs%3600)//60}m"
            else:
                remain = f" — còn {secs//60}m"
        lines.append(f"🔥 *PROMO*: ~{fmt_usdt(p.original_price)}~ → *{fmt_usdt(p.price)}* USDT{remain}")
    else:
        lines.append(f"{t(lang,'orig_price')}: {fmt_usdt(p.price)} USDT")
    lines.append(f"{t(lang,'stock_now')}: {stock_str}")
    if p.max_qty:
        lines.append(t(lang, "max_per_order", n=p.max_qty))
    lines.append(f"{t(lang,'warranty')}: {p.warranty}")
    if p.discount_tiers:
        lines.append("")
        for tier in p.discount_tiers:
            lines.append(
                t(lang, "promo", min=int(tier["min"]), percent=tier["percent"])
            )
    lines.append("")
    lines.append(f"{t(lang,'qty')}: {qty}")
    lines.append(f"{t(lang,'total')}: {fmt_usdt(total)} USDT")
    lines.append(f"{t(lang,'wallet')}: {fmt_usdt(balance)} USDT")
    text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=numpad(lang, p.id, qty), parse_mode="Markdown")
    except Exception:
        await cb.message.answer(text, reply_markup=numpad(lang, p.id, qty), parse_mode="Markdown")


@router.callback_query(F.data.startswith("prod:"))
async def product(cb: CallbackQuery, state: FSMContext) -> None:
    pid = int(cb.data.split(":")[1])
    p = await get_product(pid)
    if not p:
        await cb.answer("Not found", show_alert=True)
        return
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await state.update_data(**{f"qty:{pid}": 0})
    await _render(cb, p, 0, user.language, user.balance)
    await cb.answer()


@router.callback_query(F.data.startswith("qty:"))
async def qty(cb: CallbackQuery, state: FSMContext) -> None:
    _, pid_s, digit = cb.data.split(":")
    pid = int(pid_s)
    data = await state.get_data()
    current = int(data.get(f"qty:{pid}", 0))
    if digit == "del":
        current = current // 10
    else:
        current = current * 10 + int(digit)
        if current > 9999:
            current = 9999
    p = await get_product(pid)
    if not p:
        await cb.answer()
        return
    if p.max_qty and current > p.max_qty:
        current = p.max_qty
    await state.update_data(**{f"qty:{pid}": current})
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await _render(cb, p, current, user.language, user.balance)
    await cb.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery, state: FSMContext) -> None:
    pid = int(cb.data.split(":")[1])
    data = await state.get_data()
    current = int(data.get(f"qty:{pid}", 0))
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    if current <= 0:
        await cb.answer("⚠️ Quantity = 0", show_alert=True)
        return
    p_view = await get_product(pid)
    # supplier orders can take a few seconds — ack the button now so Telegram doesn't time out
    acked = bool(p_view and p_view.max_qty)
    if acked:
        await cb.answer("⏳")
    try:
        result = await buy_product(user.id, pid, current)
    except BuyError as e:
        code = str(e)
        key = code if code in ("insufficient", "no_stock", "max_qty", "supplier_down") else "no_stock"
        msg = t(lang, key, n=(p_view.max_qty if p_view else ""))
        if acked:
            await cb.message.answer(msg)
        else:
            await cb.answer(msg, show_alert=True)
        return

    await state.update_data(**{f"qty:{pid}": 0})
    if result.status == "pending":
        text = t(lang, "supplier_pending", id=result.order_id, total=fmt_usdt(result.total))
        if result.payloads:
            text += "\n\n" + "\n\n".join(f"`{p}`" for p in result.payloads)
    else:
        joined = "\n\n".join(f"`{p}`" for p in result.payloads)
        text = t(
            lang,
            "buy_success",
            qty=result.quantity,
            name=result.product_name,
            total=fmt_usdt(result.total),
            payload=joined,
        )
        if result.refunded > 0:
            text += "\n\n" + t(lang, "supplier_partial_refund", amount=fmt_usdt(result.refunded))
    try:
        await cb.message.answer(text, parse_mode="Markdown")
    except Exception:
        # supplier payloads may contain Markdown-breaking characters (_ * `)
        await cb.message.answer(text)
    await notify_balance_change(user.id, -result.total, f"order:{result.order_id}")
    # Admin notification (esp. for unlimited products that need manual fulfillment)
    p_obj = await get_product(pid)
    if p_obj and p_obj.unlimited:
        from bot.bot_instance import notify_admin
        await notify_admin(
            f"🛒 *NEW ORDER #{result.order_id}* — needs manual fulfillment\n"
            f"User: {user.full_name or '—'} (@{user.username or '—'}) `{user.id}`\n"
            f"Product: {result.product_name}\n"
            f"Qty: {result.quantity} | Total: {fmt_usdt(result.total)} USDT"
        )
    # re-render with zero qty
    p = await get_product(pid)
    fresh = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if p:
        await _render(cb, p, 0, lang, fresh.balance)
    if not acked:
        await cb.answer("✅")


@router.callback_query(F.data.startswith("share:"))
async def share(cb: CallbackQuery) -> None:
    pid = int(cb.data.split(":")[1])
    p = await get_product(pid)
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if not p:
        await cb.answer()
        return
    link = f"https://t.me/{settings.bot_username}?start=ref_{user.ref_code}"
    text = t(user.language, "share_text", bot=settings.bot_username, name=p.name) + f"\n{link}"
    await cb.message.answer(text)
    await cb.answer("🔗")


@router.callback_query(F.data.startswith("note:"))
async def note(cb: CallbackQuery) -> None:
    pid = int(cb.data.split(":")[1])
    p = await get_product(pid)
    if not p:
        await cb.answer()
        return
    await cb.answer(p.note or p.description or "—", show_alert=True)
