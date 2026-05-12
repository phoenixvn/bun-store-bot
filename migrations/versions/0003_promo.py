"""products promo fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-04 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("promo_price", sa.Numeric(18, 4), nullable=True))
    op.add_column(
        "products",
        sa.Column("promo_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "promo_until")
    op.drop_column("products", "promo_price")
