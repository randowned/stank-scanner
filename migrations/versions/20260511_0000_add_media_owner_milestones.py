"""add media_owner_milestones table

Tracks milestone thresholds that have been announced for media owners
(channels/artists). Mirrors the media_milestones pattern but keyed by
media_owner_id instead of media_item_id.

Revision ID: f4g5h6i7j8k9
Revises: e2f3g4h5i6j7
Create Date: 2026-05-11 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f4g5h6i7j8k9"
down_revision: str | Sequence[str] | None = "e2f3g4h5i6j7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_owner_milestones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "media_owner_id",
            sa.Integer(),
            sa.ForeignKey("media_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_key", sa.String(32), nullable=False),
        sa.Column("milestone_value", sa.BigInteger(), nullable=False),
        sa.Column(
            "announced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "media_owner_id", "metric_key", "milestone_value",
            name="uq_owner_milestone",
        ),
    )


def downgrade() -> None:
    op.drop_table("media_owner_milestones")
