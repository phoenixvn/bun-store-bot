from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database import session_scope
from bot.i18n import t
from bot.keyboards import cancel_kb, deposit_menu
from bot.models import Deposit, DepositStatus
from bot.payments.binance_pay import verify_order_id
from bot.payments.common import record_and_credit
from bot.services import get_or_create_user
from bot.utils import fmt_usdt, parse_decimal

router = Router()


class DepositFSM(StatesGroup):
    binance_order_id = State()
    bep20_amount = State()
    ton_amount = State()
    tron_amount = State()


@router.callback_query(F.data == "dep:menu")
async def menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await cb.message.edit_text(t(user.language, "deposit_menu"), reply_markup=deposit_menu(user.language))
    await cb.answer()


@router.callback_query(F.data == "dep:binance")
async def binance(cb: CallbackQuery, state: FSMContext) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await state.set_state(DepositFSM.binance_order_id)
    text = t(
        user.language,
        "binance_instructions",
        pay_id=settings.binance_pay_id,
        pay_name=settings.binance_pay_name,
    )
    await cb.message.edit_text(text, reply_markup=cancel_kb(user.language, "dep:menu"), parse_mode="Markdown")
    await cb.answer()


@router.message(StateFilter(DepositFSM.binance_order_id))
async def binance_order(msg: Message, state: FSMContext) -> None:
    user = await get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    order_id = (msg.text or "").strip()
    if len(order_id) < 6:
        await msg.answer(t(user.language, "deposit_invalid"))
        return
    amount = await verify_order_id(order_id)
    if amount is None or amount <= 0:
        await msg.answer(t(user.language, "deposit_invalid"))
        return
    ok, new_bal = await record_and_credit(user.id, "binance_pay", order_id, amount)
    if not ok:
        await msg.answer(t(user.language, "deposit_invalid"))
        return
    await state.clear()
    await msg.answer(
        t(user.language, "deposit_received", amount=fmt_usdt(amount), balance=fmt_usdt(new_bal))
    )


async def _prompt_amount(cb: CallbackQuery, state: FSMContext, method: str, key_tpl: str, addr: str):
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    mapping = {
        "bep20": DepositFSM.bep20_amount,
        "ton": DepositFSM.ton_amount,
        "tron": DepositFSM.tron_amount,
    }
    await state.set_state(mapping[method])
    text = (
        t(user.language, key_tpl, address=addr)
        + "\n\n_Nhập số tiền bạn sẽ gửi (VD: 5.25):_"
    )
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


@router.message(StateFilter(DepositFSM.bep20_amount, DepositFSM.ton_amount, DepositFSM.tron_amount))
async def amount_entered(msg: Message, state: FSMContext) -> None:
    user = await get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    cur = await state.get_state()
    method = {
        DepositFSM.bep20_amount.state: "bep20",
        DepositFSM.ton_amount.state: "ton",
        DepositFSM.tron_amount.state: "tron",
    }[cur]
    amount = parse_decimal(msg.text or "")
    if not amount:
        await msg.answer("❌ Số tiền không hợp lệ.")
        return
    await _register_pending(user.id, method, amount)
    await state.clear()
    await msg.answer(
        f"⏳ Phiên nạp {method.upper()} đã đăng ký: {fmt_usdt(amount)}\n"
        f"Vui lòng gửi *chính xác* số tiền đến địa chỉ đã cung cấp. Bot sẽ tự động ghi nhận.",
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
