"""Add slug to media_items, media reply settings, and media embed templates.

Revision ID: add_media_slug
Revises: add_media_tables
Create Date: 2026-04-30 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import String, text

revision = "add_media_slug"
down_revision = "add_media_tables"


def upgrade() -> None:
    op.add_column("media_items", op.Column("slug", String(64), nullable=True))
    op.create_unique_constraint("uq_media_slug", "media_items", ["guild_id", "slug"])


def downgrade() -> None:
    op.drop_constraint("uq_media_slug", "media_items", type_="unique")
    op.drop_column("media_items", "slug")
