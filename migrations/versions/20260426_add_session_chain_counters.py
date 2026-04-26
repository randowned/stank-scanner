"""Add session counters to player_totals and create player_chain_totals table.

Revision ID: add_session_chain_counters
Revises: c0d3f4e5a6b7
Create Date: 2026-04-26 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "add_session_chain_counters"
down_revision = "c0d3f4e5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_totals",
        sa.Column("stanks_in_session", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_totals",
        sa.Column("reactions_in_session", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "player_chain_totals",
        sa.Column(
            "guild_id",
            sa.BigInteger(),
            sa.ForeignKey("guilds.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("chain_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("stanks_in_chain", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reactions_in_chain", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("player_chain_totals")
    op.drop_column("player_totals", "reactions_in_session")
    op.drop_column("player_totals", "stanks_in_session")