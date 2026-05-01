"""init

Revision ID: 0001
Revises:
Create Date: 2026-04-24 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(64)),
        sa.Column("full_name", sa.String(128)),
        sa.Column("balance", sa.Numeric(18, 4), server_default="0"),
        sa.Column("language", sa.String(8), server_default="vi"),
        sa.Column("notifications", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("referrer_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("ref_code", sa.String(16), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("support_topic_id", sa.Integer()),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("emoji", sa.String(16), server_default=""),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("warranty", sa.String(128), server_default="Không có bảo hành"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("note", sa.Text(), server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("unlimited", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("discount_tiers", sa.JSON(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id")),
        sa.Column("product_name", sa.String(128)),
        sa.Column("quantity", sa.Integer()),
        sa.Column("unit_price", sa.Numeric(18, 4)),
        sa.Column("total", sa.Numeric(18, 4)),
        sa.Column("discount_percent", sa.Numeric(6, 2), server_default="0"),
        sa.Column("status", sa.String(32), server_default="completed"),
        sa.Column("expired", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("via_api", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "stock_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), index=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("sold", sa.Boolean(), server_default=sa.text("false"), index=True),
        sa.Column("sold_at", sa.DateTime(timezone=True)),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="SET NULL")),
    )
    op.create_table(
        "deposits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("method", sa.String(32)),
        sa.Column("amount", sa.Numeric(18, 4)),
        sa.Column("status", sa.String(16), server_default="pending", index=True),
        sa.Column("external_id", sa.String(128), index=True),
        sa.Column("raw", sa.JSON(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("method", "external_id", name="uq_deposit_method_extid"),
    )
    op.create_table(
        "referral_earnings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("referee_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("deposit_id", sa.Integer(), sa.ForeignKey("deposits.id")),
        sa.Column("amount", sa.Numeric(18, 4)),
        sa.Column("transferred", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("withdrawn", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "api_keys",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("webhook_url", sa.String(512)),
        sa.Column("api_orders", sa.Integer(), server_default="0"),
        sa.Column("api_spend", sa.Numeric(18, 4), server_default="0"),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("api_keys")
    op.drop_table("referral_earnings")
    op.drop_table("deposits")
    op.drop_table("stock_items")
    op.drop_table("orders")
    op.drop_table("products")
    op.drop_table("users")
