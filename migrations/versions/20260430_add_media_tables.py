"""Add media_items, metric_cache, and metric_snapshots tables.

Revision ID: add_media_tables
Revises: add_session_chain_counters
Create Date: 2026-04-30 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func

revision = "add_media_tables"
down_revision = "add_session_chain_counters"


def upgrade() -> None:
    op.create_table(
        "media_items",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("guild_id", BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        Column("media_type", String(32), nullable=False),
        Column("external_id", String(128), nullable=False),
        Column("title", String(500), nullable=False),
        Column("channel_name", String(255), nullable=True),
        Column("channel_id", String(128), nullable=True),
        Column("thumbnail_url", String(500), nullable=True),
        Column("published_at", DateTime(timezone=True), nullable=True),
        Column("duration_seconds", Integer, nullable=True),
        Column("added_by", BigInteger, nullable=False),
        Column("metrics_last_fetched_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        UniqueConstraint("guild_id", "media_type", "external_id", name="uq_media_item_unique"),
    )

    op.create_table(
        "metric_cache",
        Column("media_item_id", Integer, ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True),
        Column("metric_key", String(32), primary_key=True),
        Column("value", BigInteger, nullable=False),
        Column("fetched_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )

    op.create_table(
        "metric_snapshots",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("media_item_id", Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False),
        Column("metric_key", String(32), nullable=False),
        Column("value", BigInteger, nullable=False),
        Column("fetched_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    op.create_index("ix_metric_snapshots_item_key_time", "metric_snapshots", ["media_item_id", "metric_key", "fetched_at"])


def downgrade() -> None:
    op.drop_table("metric_snapshots")
    op.drop_table("metric_cache")
    op.drop_table("media_items")
