"""add media_milestones table

Revision ID: a1b2c3d4e5f6
Revises: b4e1f9a2c7d3
Create Date: 2026-05-06 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = 'b4e1f9a2c7d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'media_milestones',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('media_item_id', sa.Integer(), nullable=False),
        sa.Column('metric_key', sa.String(length=32), nullable=False),
        sa.Column('milestone_value', sa.BigInteger(), nullable=False),
        sa.Column('announced_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['media_item_id'], ['media_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('media_item_id', 'metric_key', 'milestone_value', name='uq_media_milestone'),
    )


def downgrade() -> None:
    op.drop_table('media_milestones')
