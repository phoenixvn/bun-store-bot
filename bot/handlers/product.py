from __future__ import annotations

from decimal import Decimal
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.i18n import t
from bot.keyboards import numpad, product_detail_kb
from bot.services import get_or_create_user
from bot.services.order import BuyError, BuyResult, ProductView, buy_product, get_product
from bot.services.webhook import notify_balance_change
from bot.ui import edit_or_send
from bot.utils import best_discount, fmt_usdt

router = Router()

HTML = "HTML"


def _price_html(p: ProductView) -> str:
    if p.original_price is not None:
        return f"<s>{fmt_usdt(p.original_price)}</s> → 🔥 <b>{fmt_usdt(p.price)} USDT</b>"
    return f"<b>{fmt_usdt(p.price)} USDT</b>"


def detail_text(p: ProductView, lang: str) -> str:
    stock = "∞" if p.unlimited else str(p.in_stock)
    lines = [f"{escape(p.emoji or '📦')} <b>{escape(p.name)}</b>", ""]
    if p.description:
        lines += [f"📝 {escape(p.description.strip())}", ""]
    lines.append(f"💰 {t(lang, 'price_label')}: {_price_html(p)}")
    lines.append(f"📦 {t(lang, 'stock_label')}: <b>{stock}</b>")
    if p.max_qty:
        lines.append(t(lang, "max_per_order", n=p.max_qty))
    if p.warranty:
        lines.append(f"🛡 {t(lang, 'warranty_label')}: {escape(p.warranty)}")
    if p.discount_tiers:
        lines.append("")
        for tier in p.discount_tiers:
            lines.append(t(lang, "promo", min=int(tier["min"]), percent=tier["percent"]))
    if p.note:
        lines += ["", f"⚠️ {escape(p.note.strip())}"]
    return "\n".join(lines)


def payloads_html(payloads: list[str]) -> str:
    return "\n\n".join(f"<code>{escape(x)}</code>" for x in payloads)


def buy_result_text(lang: str, r: BuyResult) -> str:
    if r.status == "pending":
        text = t(lang, "supplier_pending", id=r.code or r.order_id, total=fmt_usdt(r.total))
        if r.payloads:
            text += "\n\n" + payloads_html(r.payloads)
        return text
    text = t(
        lang,
        "buy_success",
        qty=r.quantity,
        name=escape(r.product_name),
        total=fmt_usdt(r.total),
        payload=payloads_html(r.payloads),
    )
    if r.code:
        text += "\n\n" + t(lang, "order_code_line", code=r.code)
    if r.refunded > 0:
        text += "\n\n" + t(lang, "supplier_partial_refund", amount=fmt_usdt(r.refunded))
    return text


# ---------------------------------------------------------------- product page

async def send_product(message: Message, user, pid: int) -> None:
    """Product page as a fresh message (deep links / restock posts)."""
    p = await get_product(pid)
    if not p:
        await message.answer(t(user.language, "no_stock"))
        return
    await message.answer(
        detail_text(p, user.language), reply_markup=product_detail_kb(user.language, p), parse_mode=HTML
    )


@router.callback_query(F.data.startswith("prod:"))
async def product(cb: CallbackQuery, state: FSMContext) -> None:
    pid = int(cb.data.split(":")[1])
    p = await get_product(pid)
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if not p:
        await cb.answer(t(user.language, "no_stock"), show_alert=True)
        return
    await state.update_data(**{f"qty:{pid}": 0})
    await edit_or_send(cb, detail_text(p, user.language), product_detail_kb(user.language, p), HTML)
    await cb.answer()


# ---------------------------------------------------------------- quantity picker

async def _render_qty(cb: CallbackQuery, p: ProductView, qty: int, lang: str, balance: Decimal):
    discount = best_discount(qty, p.discount_tiers)
    unit = Decimal(p.price)
    total = (unit * qty * (Decimal("100") - discount) / Decimal("100")).quantize(Decimal("0.0001"))
    stock = "∞" if p.unlimited else str(p.in_stock)
    lines = [
        f"🛒 <b>{escape(p.name)}</b>",
        f"💰 {t(lang, 'price_label')}: {_price_html(p)}",
        f"📦 {t(lang, 'stock_label')}: {stock}",
    ]
    if p.max_qty:
        lines.append(t(lang, "max_per_order", n=p.max_qty))
    lines += [
        "",
        f"{t(lang, 'qty')}: <b>{qty}</b>",
        f"{t(lang, 'total')}: <b>{fmt_usdt(total)} USDT</b>" + (f" (-{discount}%)" if discount else ""),
        f"{t(lang, 'wallet')}: {fmt_usdt(balance)} USDT",
    ]
    if total > balance:
        lines.append(t(lang, "need_topup", amount=fmt_usdt(total - balance)))
    await edit_or_send(cb, "\n".join(lines), numpad(lang, p.id, qty), HTML)


async def _set_qty(cb: CallbackQuery, state: FSMContext, pid: int, qty: int) -> None:
    p = await get_product(pid)
    if not p:
        await cb.answer()
        return
    if p.max_qty and qty > p.max_qty:
        qty = p.max_qty
    if not p.unlimited and qty > p.in_stock:
        qty = max(0, p.in_stock)
    await state.update_data(**{f"qty:{pid}": qty})
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await _render_qty(cb, p, qty, user.language, user.balance)
    await cb.answer()


@router.callback_query(F.data.startswith("pbuy:"))
async def pick_qty(cb: CallbackQuery, state: FSMContext) -> None:
    await _set_qty(cb, state, int(cb.data.split(":")[1]), 1)


@router.callback_query(F.data.startswith("qset:"))
async def quick_qty(cb: CallbackQuery, state: FSMContext) -> None:
    _, pid_s, n = cb.data.split(":")
    await _set_qty(cb, state, int(pid_s), int(n))


@router.callback_query(F.data.startswith("qty:"))
async def qty(cb: CallbackQuery, state: FSMContext) -> None:
    _, pid_s, digit = cb.data.split(":")
    pid = int(pid_s)
    current = int((await state.get_data()).get(f"qty:{pid}", 0))
    if digit == "del":
        current = current // 10
    else:
        current = min(9999, current * 10 + int(digit))
    await _set_qty(cb, state, pid, current)


# ---------------------------------------------------------------- buy

@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery, state: FSMContext) -> None:
    pid = int(cb.data.split(":")[1])
    current = int((await state.get_data()).get(f"qty:{pid}", 0))
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    if current <= 0:
        await cb.answer(t(lang, "qty_zero"), show_alert=True)
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
    # delivered goods go in their own message so they stay in the chat history
    await cb.message.answer(buy_result_text(lang, result), parse_mode=HTML)
    await notify_balance_change(user.id, -result.total, f"order:{result.order_id}")
    p_obj = await get_product(pid)
    if p_obj and p_obj.unlimited:
        from bot.bot_instance import notify_admin

        await notify_admin(
            f"🛒 NEW ORDER #{result.code or result.order_id} — needs manual fulfillment\n"
            f"User: {user.full_name or '—'} (@{user.username or '—'}) {user.id}\n"
            f"Product: {result.product_name}\n"
            f"Qty: {result.quantity} | Total: {fmt_usdt(result.total)} USDT",
            parse_mode=None,
        )
    if p_obj:
        await edit_or_send(cb, detail_text(p_obj, lang), product_detail_kb(lang, p_obj), HTML)
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
    await cb.answer((p.note or p.description or "—")[:200], show_alert=True)
