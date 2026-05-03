"""add_alignment_mask to metric_snapshots

Revision ID: 3f927e7ca474
Revises: d71b13e08cba
Create Date: 2026-05-03 19:35:00.457879+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '3f927e7ca474'
down_revision: str | Sequence[str] | None = 'd71b13e08cba'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, col: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return col in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    if not _has_column('metric_snapshots', 'alignment_mask'):
        with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
            batch_op.add_column(sa.Column('alignment_mask', sa.Integer(), nullable=True))

    # collection_interval_minutes was added in v2.43.1; drop it if present
    # so it doesn't conflict with the model which now uses alignment_mask.
    if _has_column('metric_snapshots', 'collection_interval_minutes'):
        with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
            batch_op.drop_column('collection_interval_minutes')


def downgrade() -> None:
    with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
        batch_op.drop_column('alignment_mask')
