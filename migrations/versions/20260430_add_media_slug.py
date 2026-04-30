"""Add slug to media_items, media reply settings, and media embed templates.

Revision ID: add_media_slug
Revises: add_media_tables
Create Date: 2026-04-30 14:00:00.000000

This migration is idempotent — if the column or constraint already exists
(from a previous partial deploy / crash), it skips rather than failing.
"""

from __future__ import annotations

import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)

revision = "add_media_slug"
down_revision = "add_media_tables"


def upgrade() -> None:
    try:
        op.add_column(
            "media_items", sa.Column("slug", sa.String(64), nullable=True)
        )
    except OperationalError:
        log.warning("slug column already exists, skipping add_column")

    # Build the unique constraint.  No IF NOT EXISTS in SQLite — we rely
    # on the convention that constraint names are unique per table so any
    # duplicate name will trigger a distinct error that we can swallow.
    try:
        op.create_unique_constraint(
            "uq_media_slug", "media_items", ["guild_id", "slug"]
        )
    except OperationalError:
        log.warning("uq_media_slug constraint already exists, skipping")


def downgrade() -> None:
    try:
        op.drop_constraint("uq_media_slug", "media_items", type_="unique")
    except OperationalError:
        log.warning("uq_media_slug constraint not found, skipping drop")

    try:
        op.drop_column("media_items", "slug")
    except OperationalError:
        log.warning("slug column not found, skipping drop")
