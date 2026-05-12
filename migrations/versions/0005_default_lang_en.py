"""default language English

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-12 00:00:00
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET language = 'en' WHERE language = 'vi'")
    op.execute("UPDATE products SET warranty = 'No warranty' WHERE warranty = 'Không có bảo hành'")


def downgrade() -> None:
    pass
