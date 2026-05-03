"""add alignment_mask covering index to metric_snapshots

Revision ID: b4e1f9a2c7d3
Revises: 3f927e7ca474
Create Date: 2026-05-03 21:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = 'b4e1f9a2c7d3'
down_revision: str | Sequence[str] | None = '3f927e7ca474'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        'ix_metric_snapshots_item_key_align_time',
        'metric_snapshots',
        ['media_item_id', 'metric_key', 'alignment_mask', 'fetched_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_metric_snapshots_item_key_align_time', table_name='metric_snapshots')
