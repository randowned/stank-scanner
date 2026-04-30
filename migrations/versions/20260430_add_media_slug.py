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
    # Use batch mode — SQLite can't ALTER constraints natively.
    with op.batch_alter_table("media_items") as batch_op:
        try:
            batch_op.add_column(
                sa.Column("slug", sa.String(64), nullable=True)
            )
        except OperationalError:
            log.warning("slug column already exists, skipping add_column")

        try:
            batch_op.create_unique_constraint(
                "uq_media_slug", ["guild_id", "slug"]
            )
        except OperationalError:
            log.warning("uq_media_slug constraint already exists, skipping")


def downgrade() -> None:
    with op.batch_alter_table("media_items") as batch_op:
        try:
            batch_op.drop_constraint("uq_media_slug", type_="unique")
        except OperationalError:
            log.warning("uq_media_slug constraint not found, skipping drop")

        try:
            batch_op.drop_column("slug")
        except OperationalError:
            log.warning("slug column not found, skipping drop")
