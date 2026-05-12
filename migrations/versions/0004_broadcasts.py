"""broadcasts table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-04 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audience", sa.String(32), nullable=False),
        sa.Column("audience_param", sa.Text(), server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("parse_mode", sa.String(16), server_default="Markdown"),
        sa.Column("to_users", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("to_channel", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("recipients", sa.Integer(), server_default="0"),
        sa.Column("sent", sa.Integer(), server_default="0"),
        sa.Column("failed", sa.Integer(), server_default="0"),
        sa.Column("channel_ok", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("broadcasts")
