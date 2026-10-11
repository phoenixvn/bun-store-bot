from __future__ import annotations

import secrets
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import settings
from bot.database import session_scope
from bot.i18n import t
from bot.keyboards import cancel_kb, deposit_menu, vietqr_amounts_kb
from bot.models import Deposit, DepositStatus
from bot.payments import cryptomus, vietqr
from bot.payments.common import record_and_credit
from bot.services import get_or_create_user
from bot.ui import edit_or_send
from bot.utils import fmt_usdt, fmt_vnd, parse_decimal

router = Router()


class DepositFSM(StatesGroup):
    binance_pay_amount = State()
    bep20_amount = State()
    ton_amount = State()
    tron_amount = State()
    binance_spot_bep20_amount = State()
    binance_spot_trc20_amount = State()
    cryptomus_amount = State()
    vietqr_amount = State()


@router.callback_query(F.data == "dep:menu")
async def menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await edit_or_send(cb, t(user.language, "deposit_menu"), deposit_menu(user.language))
    await cb.answer()


# ---------------------------------------------------------------- VietQR (bank transfer)

@router.callback_query(F.data == "dep:vqr")
async def vietqr_pick(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    if not vietqr.enabled():
        await cb.answer(t(lang, "vqr_disabled"), show_alert=True)
        return
    text = t(
        lang,
        "vqr_prompt",
        min=fmt_vnd(settings.vietqr_min_vnd),
        rate=fmt_vnd(settings.vnd_per_usdt),
    )
    await edit_or_send(cb, text, vietqr_amounts_kb(lang), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "dep:vqr:custom")
async def vietqr_custom(cb: CallbackQuery, state: FSMContext) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await state.set_state(DepositFSM.vietqr_amount)
    await edit_or_send(
        cb,
        t(user.language, "vqr_enter_amount", min=fmt_vnd(settings.vietqr_min_vnd)),
        cancel_kb(user.language, "dep:vqr"),
    )
    await cb.answer()


async def _send_vietqr(target: Message, user, vnd: int) -> None:
    lang = user.language
    dep_id, memo, usdt = await vietqr.create_session(user.id, vnd)
    caption = t(
        lang,
        "vqr_caption",
        vnd=fmt_vnd(vnd),
        usdt=fmt_usdt(usdt),
        bank=settings.bank_code,
        account=settings.bank_account,
        name=settings.bank_account_name or "—",
        memo=memo,
    )
    caption += "\n\n" + t(lang, "vqr_auto" if vietqr.auto_confirm() else "vqr_manual")
    rows = []
    if not vietqr.auto_confirm():
        rows.append([InlineKeyboardButton(text=t(lang, "vqr_done_btn"), callback_data=f"dep:vqrdone:{dep_id}")])
    rows.append([InlineKeyboardButton(text=t(lang, "main_menu_btn"), callback_data="menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await target.answer_photo(vietqr.qr_url(vnd, memo), caption=caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        # QR image service unreachable — the account details alone are enough to pay
        await target.answer(caption, reply_markup=kb, parse_mode="HTML")


def _parse_vnd(text: str) -> int | None:
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    if not digits:
        return None
    v = int(digits)
    if (text or "").strip().lower().endswith("k"):
        v *= 1000
    return v


@router.callback_query(F.data.startswith("dep:vqr:"))
async def vietqr_amount_btn(cb: CallbackQuery, state: FSMContext) -> None:
    raw = cb.data.split(":")[2]
    if not raw.isdigit():
        await cb.answer()
        return
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if not vietqr.enabled():
        await cb.answer(t(user.language, "vqr_disabled"), show_alert=True)
        return
    await state.clear()
    await cb.answer()
    await _send_vietqr(cb.message, user, int(raw))


@router.message(StateFilter(DepositFSM.vietqr_amount))
async def vietqr_amount_entered(msg: Message, state: FSMContext) -> None:
    user = await get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    lang = user.language
    vnd = _parse_vnd(msg.text or "")
    if not vnd or vnd < settings.vietqr_min_vnd or vnd > 100_000_000:
        await msg.answer(t(lang, "vqr_enter_amount", min=fmt_vnd(settings.vietqr_min_vnd)))
        return
    await state.clear()
    await _send_vietqr(msg, user, vnd)


@router.callback_query(F.data.startswith("dep:vqrdone:"))
async def vietqr_done(cb: CallbackQuery) -> None:
    """Manual mode (no SePay): user says they paid -> ping admin to approve."""
    from bot.bot_instance import notify_admin

    dep_id = int(cb.data.split(":")[2])
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    async with session_scope() as s:
        d = await s.get(Deposit, dep_id)
        if not d or d.user_id != user.id or d.status != DepositStatus.PENDING.value:
            await cb.answer("✅")
            return
        memo, vnd, usdt = d.external_id, (d.raw or {}).get("vnd"), d.amount
    await notify_admin(
        f"🏦 VietQR top-up claimed — check the bank and approve deposit #{dep_id} at /admin/deposits\n"
        f"User: {user.full_name or '—'} (@{user.username or '—'}) {user.id}\n"
        f"Amount: {int(vnd or 0):,} VND = {usdt} USDT | Memo: {memo}",
        parse_mode=None,
    )
    await cb.answer(t(user.language, "vqr_claimed"), show_alert=True)


@router.callback_query(F.data == "dep:binance")
async def binance(cb: CallbackQuery, state: FSMContext) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await state.set_state(DepositFSM.binance_pay_amount)
    text = t(
        user.language,
        "binance_instructions",
        pay_id=settings.binance_pay_id,
        pay_name=settings.binance_pay_name,
    )
    await cb.message.edit_text(text, reply_markup=cancel_kb(user.language, "dep:menu"), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "dep:cryptomus")
async def cryptomus_pick(cb: CallbackQuery, state: FSMContext) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if not cryptomus.enabled():
        await cb.answer(t(user.language, "cryptomus_error"), show_alert=True)
        return
    await state.set_state(DepositFSM.cryptomus_amount)
    await cb.message.edit_text(
        t(user.language, "cryptomus_prompt"),
        reply_markup=cancel_kb(user.language, "dep:menu"),
        parse_mode="Markdown",
    )
    await cb.answer()


@router.message(StateFilter(DepositFSM.cryptomus_amount))
async def cryptomus_amount_entered(msg: Message, state: FSMContext) -> None:
    user = await get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    lang = user.language
    amount = parse_decimal(msg.text or "")
    if not amount or amount < Decimal("1"):
        await msg.answer(t(lang, "cryptomus_min"))
        return
    amount = amount.quantize(Decimal("0.01"))
    await state.clear()
    wait = await msg.answer(t(lang, "cryptomus_creating"))
    res = await cryptomus.create_invoice(user.id, amount)
    if not res or not res.get("url"):
        await wait.edit_text(t(lang, "cryptomus_error"))
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "cryptomus_pay_btn", amount=amount), url=res["url"])],
            [InlineKeyboardButton(text=t(lang, "back"), callback_data="dep:menu")],
        ]
    )
    await wait.edit_text(
        t(lang, "cryptomus_created", amount=amount),
        reply_markup=kb,
        parse_mode="Markdown",
    )


async def _prompt_amount(cb: CallbackQuery, state: FSMContext, method: str, key_tpl: str, addr: str):
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    mapping = {
        "bep20": DepositFSM.bep20_amount,
        "ton": DepositFSM.ton_amount,
        "tron": DepositFSM.tron_amount,
        "binance_spot_bep20": DepositFSM.binance_spot_bep20_amount,
        "binance_spot_trc20": DepositFSM.binance_spot_trc20_amount,
    }
    await state.set_state(mapping[method])
    text = t(user.language, key_tpl, address=addr) + "\n\n" + t(user.language, "enter_amount_hint")
    await cb.message.edit_text(text, reply_markup=cancel_kb(user.language, "dep:menu"), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "dep:bep20")
async def bep20_pick(cb: CallbackQuery, state: FSMContext):
    await _prompt_amount(cb, state, "bep20", "bep20_instructions", settings.bep20_deposit_address or "—")


@router.callback_query(F.data == "dep:ton")
async def ton_pick(cb: CallbackQuery, state: FSMContext):
    await _prompt_amount(cb, state, "ton", "ton_instructions", settings.ton_deposit_address or "—")


@router.callback_query(F.data == "dep:tron")
async def tron_pick(cb: CallbackQuery, state: FSMContext):
    await _prompt_amount(cb, state, "tron", "tron_instructions", settings.tron_deposit_address or "—")


@router.callback_query(F.data == "dep:bnb_spot_bep20")
async def bnb_spot_bep20_pick(cb: CallbackQuery, state: FSMContext):
    await _prompt_amount(
        cb, state, "binance_spot_bep20", "binance_spot_bep20_instructions",
        settings.binance_bep20_address or "—",
    )


@router.callback_query(F.data == "dep:bnb_spot_trc20")
async def bnb_spot_trc20_pick(cb: CallbackQuery, state: FSMContext):
    await _prompt_amount(
        cb, state, "binance_spot_trc20", "binance_spot_trc20_instructions",
        settings.binance_trc20_address or "—",
    )


async def _register_pending(user_id: int, method: str, amount: Decimal) -> int:
    async with session_scope() as s:
        dep = Deposit(
            user_id=user_id,
            method=method,
            amount=amount,
            status=DepositStatus.PENDING.value,
            external_id=None,
        )
        s.add(dep)
        await s.flush()
        return dep.id


@router.message(
    StateFilter(
        DepositFSM.binance_pay_amount,
        DepositFSM.bep20_amount,
        DepositFSM.ton_amount,
        DepositFSM.tron_amount,
        DepositFSM.binance_spot_bep20_amount,
        DepositFSM.binance_spot_trc20_amount,
    )
)
async def amount_entered(msg: Message, state: FSMContext) -> None:
    user = await get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    lang = user.language
    cur = await state.get_state()
    method = {
        DepositFSM.binance_pay_amount.state: "binance_pay",
        DepositFSM.bep20_amount.state: "bep20",
        DepositFSM.ton_amount.state: "ton",
        DepositFSM.tron_amount.state: "tron",
        DepositFSM.binance_spot_bep20_amount.state: "binance_spot",
        DepositFSM.binance_spot_trc20_amount.state: "binance_spot",
    }[cur]
    amount = parse_decimal(msg.text or "")
    if not amount:
        await msg.answer(t(lang, "invalid_amount"))
        return
    # Add random 4th-decimal suffix (0.0001..0.0099) so two users entering
    # the same headline amount don't collide on the poller match-by-amount.
    suffix = (secrets.randbelow(99) + 1)
    amount = (amount.quantize(Decimal("0.0001")) + Decimal(suffix) / Decimal("10000")).quantize(Decimal("0.0001"))
    await _register_pending(user.id, method, amount)
    await state.clear()
    await msg.answer(
        t(lang, "pending_registered", amount=amount, interval=settings.deposit_poll_interval),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "dep:other")
async def other(cb: CallbackQuery) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await cb.message.edit_text(
        t(user.language, "other_instructions"),
        reply_markup=cancel_kb(user.language, "dep:menu"),
    )
    await cb.answer()
