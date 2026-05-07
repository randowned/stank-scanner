"""add guild_members table

Write-through cache of Discord member identity (roles, permissions, nick,
username, avatar). Populated on first stank / dashboard visit, kept fresh
by member_update / member_remove Gateway events. Used as the primary
display-name/avatar source for the dashboard.

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6
Create Date: 2026-05-07 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guild_members",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("permissions", sa.BigInteger(), nullable=False, server_default=sa.text("'0'")),
        sa.Column("nick", sa.String(length=100), nullable=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("global_name", sa.String(length=100), nullable=True),
        sa.Column("avatar", sa.String(length=100), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("guild_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("guild_members")
