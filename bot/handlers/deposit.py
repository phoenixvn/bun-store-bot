from __future__ import annotations

import secrets
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
from bot.payments.common import record_and_credit
from bot.services import get_or_create_user
from bot.utils import fmt_usdt, parse_decimal

router = Router()


class DepositFSM(StatesGroup):
    binance_pay_amount = State()
    bep20_amount = State()
    ton_amount = State()
    tron_amount = State()
    binance_spot_bep20_amount = State()
    binance_spot_trc20_amount = State()


@router.callback_query(F.data == "dep:menu")
async def menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await cb.message.edit_text(t(user.language, "deposit_menu"), reply_markup=deposit_menu(user.language))
    await cb.answer()


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
        await msg.answer("❌ Số tiền không hợp lệ.")
        return
    # Add random 4th-decimal suffix (0.0001..0.0099) so two users entering
    # the same headline amount don't collide on the poller match-by-amount.
    suffix = (secrets.randbelow(99) + 1)
    amount = (amount.quantize(Decimal("0.0001")) + Decimal(suffix) / Decimal("10000")).quantize(Decimal("0.0001"))
    await _register_pending(user.id, method, amount)
    await state.clear()
    await msg.answer(
        f"⏳ Phiên nạp đã đăng ký.\n\n"
        f"Vui lòng gửi *chính xác* số tiền:\n`{amount}` USDT\n\n"
        f"⚠️ _Đúng cả 4 chữ số thập phân_ — sai 1 số bot sẽ không tự ghi nhận. Bot polling mỗi 30 giây.",
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
