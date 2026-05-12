"""products.cost_price

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-03 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("cost_price", sa.Numeric(18, 4), nullable=True))
    # Recover cost from existing prices: current price = cost * 1.30 (single markup applied so far)
    op.execute("UPDATE products SET cost_price = (price / 1.30) WHERE cost_price IS NULL")


def downgrade() -> None:
    op.drop_column("products", "cost_price")
