from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DepositStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DepositMethod(str, enum.Enum):
    BINANCE_PAY = "binance_pay"
    BEP20 = "bep20"
    TON = "ton"
    TRON = "tron"
    OTHER = "other"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram id
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    language: Mapped[str] = mapped_column(String(8), default="en")
    notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    referrer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ref_code: Mapped[str] = mapped_column(String(16), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # support session — forum topic id in support group
    support_topic_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    api_key: Mapped[Optional["ApiKey"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    emoji: Mapped[str] = mapped_column(String(16), default="")
    cost_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    promo_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    promo_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    warranty: Mapped[str] = mapped_column(String(128), default="No warranty")
    description: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    unlimited: Mapped[bool] = mapped_column(Boolean, default=False)  # ∞ stock (digital)
    discount_tiers: Mapped[list] = mapped_column(JSON, default=list)
    # [{"min": 5, "percent": 5.0}, {"min": 15, "percent": 12.0}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock_items: Mapped[list["StockItem"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[str] = mapped_column(Text)  # the key/account text delivered
    sold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    product: Mapped[Product] = relationship(back_populates="stock_items")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(32), default="completed")  # completed | refunded
    expired: Mapped[bool] = mapped_column(Boolean, default=False)  # warranty expired flag
    via_api: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Deposit(Base):
    __tablename__ = "deposits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    status: Mapped[str] = mapped_column(String(16), default=DepositStatus.PENDING.value, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("method", "external_id", name="uq_deposit_method_extid"),)


class ReferralEarning(Base):
    __tablename__ = "referral_earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    referee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    deposit_id: Mapped[int] = mapped_column(ForeignKey("deposits.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    transferred: Mapped[bool] = mapped_column(Boolean, default=False)
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    api_orders: Mapped[int] = mapped_column(Integer, default=0)
    api_spend: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="api_key")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audience: Mapped[str] = mapped_column(String(32))  # all|depositors|buyers|has_balance|by_lang|ids|none
    audience_param: Mapped[str] = mapped_column(Text, default="")  # lang code or comma-separated ids
    text: Mapped[str] = mapped_column(Text)
    parse_mode: Mapped[str] = mapped_column(String(16), default="Markdown")
    to_users: Mapped[bool] = mapped_column(Boolean, default=True)
    to_channel: Mapped[bool] = mapped_column(Boolean, default=False)
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    channel_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
