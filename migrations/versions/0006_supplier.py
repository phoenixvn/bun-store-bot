"""FatCat supplier integration: product link + order fulfillment tracking

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("supplier_product_id", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("supplier_price_vnd", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("supplier_stock", sa.Integer(), server_default="0", nullable=False))
    op.add_column("products", sa.Column("supplier_max_qty", sa.Integer(), server_default="50", nullable=False))
    op.add_column("products", sa.Column("supplier_available", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("products", sa.Column("supplier_auto_price", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.create_index("ix_products_supplier_product_id", "products", ["supplier_product_id"], unique=True)

    op.add_column("orders", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("supplier_order_id", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("supplier_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("supplier_error", sa.Text(), nullable=True))
    op.create_index("ix_orders_request_id", "orders", ["request_id"], unique=True)
    op.create_index("ix_orders_status", "orders", ["status"])


def downgrade() -> None:
    op.drop_index("ix_orders_status", "orders")
    op.drop_index("ix_orders_request_id", "orders")
    for c in ("supplier_error", "supplier_attempts", "supplier_order_id", "request_id"):
        op.drop_column("orders", c)
    op.drop_index("ix_products_supplier_product_id", "products")
    for c in (
        "supplier_auto_price",
        "supplier_available",
        "supplier_max_qty",
        "supplier_stock",
        "supplier_price_vnd",
        "supplier_product_id",
    ):
        op.drop_column("products", c)
