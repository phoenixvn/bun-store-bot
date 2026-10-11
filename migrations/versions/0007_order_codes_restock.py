"""order codes (#DHxxxxxxx) + restock notification cooldown

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-11 00:00:00
"""
import secrets
import string

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_ALPHABET = string.ascii_uppercase + string.digits


def _code() -> str:
    return "DH" + "".join(secrets.choice(_ALPHABET) for _ in range(7))


def upgrade() -> None:
    op.add_column("orders", sa.Column("code", sa.String(16), nullable=True))
    op.add_column("products", sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True))

    # backfill existing orders before the unique index exists
    bind = op.get_bind()
    ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM orders WHERE code IS NULL"))]
    used: set[str] = set()
    for oid in ids:
        c = _code()
        while c in used:
            c = _code()
        used.add(c)
        bind.execute(sa.text("UPDATE orders SET code = :c WHERE id = :i"), {"c": c, "i": oid})
    op.create_index("ix_orders_code", "orders", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_orders_code", "orders")
    op.drop_column("orders", "code")
    op.drop_column("products", "last_notified_at")
