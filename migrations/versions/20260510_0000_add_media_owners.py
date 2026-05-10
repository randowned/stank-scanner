"""add media_owners and media_owner_snapshots tables

Global (not per-guild) owner metadata for YouTube channels and Spotify
artists, plus time-series metric snapshots mirroring the MetricSnapshot
pattern but scoped to owners instead of media items.

Revision ID: e2f3g4h5i6j7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-10 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3g4h5i6j7"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_owners",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("external_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("media_type", "external_id", name="uq_media_owner_unique"),
    )

    op.create_table(
        "media_owner_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "media_owner_id",
            sa.Integer(),
            sa.ForeignKey("media_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_key", sa.String(32), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_owner_snapshots_id_key_time",
        "media_owner_snapshots",
        ["media_owner_id", "metric_key", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_owner_snapshots_id_key_time", table_name="media_owner_snapshots")
    op.drop_table("media_owner_snapshots")
    op.drop_table("media_owners")
