from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select

from bot.config import settings
from bot.database import session_scope
from bot.models import Deposit, DepositStatus, Order, Product, StockItem, User
from bot.payments.common import record_and_credit

router = Router()


def is_admin(uid: int) -> bool:
    return uid in settings.admin_ids


class ProductFSM(StatesGroup):
    name = State()
    price = State()
    emoji = State()
    warranty = State()
    note = State()
    discount = State()


class StockFSM(StatesGroup):
    keys = State()


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add product", callback_data="adm:addp")],
            [InlineKeyboardButton(text="📦 Add stock", callback_data="adm:addstock")],
            [InlineKeyboardButton(text="📋 Products", callback_data="adm:list")],
            [InlineKeyboardButton(text="💸 Pending deposits", callback_data="adm:deps")],
            [InlineKeyboardButton(text="📊 Stats", callback_data="adm:stats")],
            [InlineKeyboardButton(text="📣 Broadcast", callback_data="adm:bcast")],
        ]
    )


@router.message(Command("admin"))
async def admin_root(msg: Message) -> None:
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Not allowed.")
        return
    await msg.answer("🛠 *Admin panel*", reply_markup=admin_kb(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("adm:"))
async def admin_actions(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    action = cb.data.split(":", 1)[1]
    if action == "addp":
        await state.set_state(ProductFSM.name)
        await cb.message.answer("📝 Tên sản phẩm:")
    elif action == "addstock":
        async with session_scope() as s:
            res = await s.execute(select(Product).order_by(Product.id))
            ps = res.scalars().all()
        rows = [
            [InlineKeyboardButton(text=f"#{p.id} {p.name}", callback_data=f"adm:stock:{p.id}")]
            for p in ps
        ]
        await cb.message.answer("Chọn sản phẩm để nạp kho:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    elif action == "list":
        async with session_scope() as s:
            res = await s.execute(select(Product).order_by(Product.id))
            ps = res.scalars().all()
            lines = []
            for p in ps:
                cnt = await s.scalar(
                    select(func.count(StockItem.id)).where(
                        StockItem.product_id == p.id, StockItem.sold.is_(False)
                    )
                )
                lines.append(f"#{p.id} {p.emoji} {p.name} — {p.price} USDT — kho: {cnt}")
        await cb.message.answer("\n".join(lines) or "Chưa có sản phẩm.")
    elif action == "deps":
        async with session_scope() as s:
            res = await s.execute(
                select(Deposit)
                .where(Deposit.status == DepositStatus.PENDING.value)
                .order_by(Deposit.id.desc())
                .limit(20)
            )
            ds = res.scalars().all()
        if not ds:
            await cb.message.answer("Không có deposit pending.")
        else:
            for d in ds:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Approve", callback_data=f"adm:dep:ok:{d.id}"),
                            InlineKeyboardButton(text="❌ Reject", callback_data=f"adm:dep:no:{d.id}"),
                        ]
                    ]
                )
                await cb.message.answer(
                    f"Deposit #{d.id}\nUser: `{d.user_id}`\nMethod: {d.method}\nAmount: {d.amount}",
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
    elif action == "stats":
        async with session_scope() as s:
            users = await s.scalar(select(func.count(User.id)))
            orders = await s.scalar(select(func.count(Order.id)))
            revenue = await s.scalar(select(func.coalesce(func.sum(Order.total), 0)))
            method_rows = (
                await s.execute(
                    select(
                        Deposit.method,
                        func.count(Deposit.id),
                        func.coalesce(func.sum(Deposit.amount), 0),
                    )
                    .where(Deposit.status == DepositStatus.APPROVED.value)
                    .group_by(Deposit.method)
                )
            ).all()
        lines = [
            f"👥 Users: {users}",
            f"📦 Orders: {orders}",
            f"💰 Revenue: {revenue} USDT",
            "",
            "*Deposits by method (A/B):*",
        ]
        if method_rows:
            for method, cnt, total in method_rows:
                lines.append(f"• `{method}` — {cnt} dep, {total} USDT")
        else:
            lines.append("_No approved deposits yet._")
        await cb.message.answer("\n".join(lines), parse_mode="Markdown")
    elif action == "bcast":
        await state.set_state("broadcast_msg")  # type: ignore
        await cb.message.answer("📣 Gửi nội dung broadcast:")
    elif action.startswith("stock:"):
        pid = int(action.split(":")[1])
        await state.set_state(StockFSM.keys)
        await state.update_data(stock_pid=pid)
        await cb.message.answer(f"📦 Dán keys cho sản phẩm #{pid}, mỗi key 1 dòng:")
    elif action.startswith("dep:ok:"):
        dep_id = int(action.split(":")[2])
        async with session_scope() as s:
            d = await s.get(Deposit, dep_id)
            if d and d.status == DepositStatus.PENDING.value:
                d.status = DepositStatus.APPROVED.value
                user_id = d.user_id
                method = d.method
                amount = d.amount
                ext = d.external_id or f"manual_{dep_id}"
        # credit through common pipeline (idempotent skips since we already approved row)
        from bot.services import credit_balance

        new_bal = await credit_balance(user_id, Decimal(amount))
        await cb.message.answer(f"✅ Approved #{dep_id}. New balance: {new_bal}")
    elif action.startswith("dep:no:"):
        dep_id = int(action.split(":")[2])
        async with session_scope() as s:
            d = await s.get(Deposit, dep_id)
            if d:
                d.status = DepositStatus.REJECTED.value
        await cb.message.answer(f"❌ Rejected #{dep_id}")
    await cb.answer()


@router.message(StateFilter(ProductFSM.name))
async def p_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(ProductFSM.price)
    await msg.answer("💲 Giá (USDT):")


@router.message(StateFilter(ProductFSM.price))
async def p_price(msg: Message, state: FSMContext):
    try:
        price = Decimal(msg.text.strip())
    except Exception:
        await msg.answer("❌ Số không hợp lệ.")
        return
    await state.update_data(price=price)
    await state.set_state(ProductFSM.emoji)
    await msg.answer("🌟 Emoji (gửi `-` để bỏ qua):")


@router.message(StateFilter(ProductFSM.emoji))
async def p_emoji(msg: Message, state: FSMContext):
    e = msg.text.strip()
    await state.update_data(emoji="" if e == "-" else e)
    await state.set_state(ProductFSM.warranty)
    await msg.answer("🛡 Bảo hành (text), `-` để bỏ qua:")


@router.message(StateFilter(ProductFSM.warranty))
async def p_warranty(msg: Message, state: FSMContext):
    w = msg.text.strip()
    await state.update_data(warranty="Không có bảo hành" if w == "-" else w)
    await state.set_state(ProductFSM.note)
    await msg.answer("📝 Ghi chú/hướng dẫn cho sản phẩm (`-` bỏ qua):")


@router.message(StateFilter(ProductFSM.note))
async def p_note(msg: Message, state: FSMContext):
    n = msg.text.strip()
    await state.update_data(note="" if n == "-" else n)
    await state.set_state(ProductFSM.discount)
    await msg.answer(
        "🎁 Bulk discount tiers JSON, vd: `[{\"min\":5,\"percent\":5},{\"min\":15,\"percent\":12}]` hoặc `-` bỏ qua",
        parse_mode="Markdown",
    )


@router.message(StateFilter(ProductFSM.discount))
async def p_discount(msg: Message, state: FSMContext):
    import json

    raw = msg.text.strip()
    tiers: list = []
    if raw != "-":
        try:
            tiers = json.loads(raw)
            assert isinstance(tiers, list)
        except Exception:
            await msg.answer("❌ JSON không hợp lệ.")
            return
    data = await state.get_data()
    async with session_scope() as s:
        p = Product(
            name=data["name"],
            emoji=data.get("emoji", ""),
            price=data["price"],
            warranty=data.get("warranty", "Không có bảo hành"),
            note=data.get("note", ""),
            discount_tiers=tiers,
        )
        s.add(p)
        await s.flush()
        pid = p.id
    await state.clear()
    await msg.answer(f"✅ Đã tạo sản phẩm #{pid}")


@router.message(StateFilter(StockFSM.keys))
async def stock_paste(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = int(data["stock_pid"])
    keys = [ln.strip() for ln in (msg.text or "").splitlines() if ln.strip()]
    if not keys:
        await msg.answer("❌ Không có key.")
        return
    async with session_scope() as s:
        for k in keys:
            s.add(StockItem(product_id=pid, payload=k))
    await state.clear()
    await msg.answer(f"✅ Đã nạp {len(keys)} key vào #{pid}")


# broadcast
@router.message(StateFilter("broadcast_msg"))
async def bcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    async with session_scope() as s:
        res = await s.execute(select(User.id))
        ids = [r[0] for r in res.all()]
    sent = 0
    for uid in ids:
        try:
            await msg.copy_to(chat_id=uid)
            sent += 1
        except Exception:
            pass
    await state.clear()
    await msg.answer(f"📣 Đã gửi tới {sent}/{len(ids)} user.")
