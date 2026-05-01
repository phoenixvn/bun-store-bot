from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.database import session_scope
from bot.i18n import t
from bot.keyboards import api_kb, cancel_kb
from bot.models import ApiKey
from bot.services import get_or_create_user
from bot.utils import fmt_usdt, gen_api_key

router = Router()


class ApiFSM(StatesGroup):
    webhook_url = State()


@router.callback_query(F.data == "api")
async def api_panel(cb: CallbackQuery) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    async with session_scope() as s:
        ak = await s.get(ApiKey, user.id)
        if not ak:
            ak = ApiKey(user_id=user.id, key=gen_api_key())
            s.add(ak)
            await s.flush()
        key = ak.key
        webhook = ak.webhook_url or "Not configured"
        orders = ak.api_orders
        spend = ak.api_spend
        active = ak.active
    text = t(
        user.language,
        "api_card",
        status="Hoạt động" if active else "Vô hiệu",
        key=key,
        webhook=webhook,
        orders=orders,
        spend=fmt_usdt(spend),
    )
    await cb.message.edit_text(text, reply_markup=api_kb(user.language), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "api:webhook")
async def webhook_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    await state.set_state(ApiFSM.webhook_url)
    await cb.message.edit_text(
        t(user.language, "set_webhook_prompt"),
        reply_markup=cancel_kb(user.language, "api"),
        parse_mode="Markdown",
    )
    await cb.answer()


@router.message(StateFilter(ApiFSM.webhook_url))
async def webhook_set(msg: Message, state: FSMContext) -> None:
    user = await get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    url = (msg.text or "").strip()
    if not url.startswith("https://"):
        await msg.answer("❌ URL phải bắt đầu với https://")
        return
    async with session_scope() as s:
        ak = await s.get(ApiKey, user.id)
        if ak:
            ak.webhook_url = url
    await state.clear()
    await msg.answer(t(user.language, "webhook_set"))


@router.callback_query(F.data == "api:revoke")
async def api_revoke(cb: CallbackQuery) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    async with session_scope() as s:
        ak = await s.get(ApiKey, user.id)
        if ak:
            ak.key = gen_api_key()
    await cb.answer(t(user.language, "api_revoked"), show_alert=True)
    await api_panel(cb)
