"""Rename media_items.slug to media_items.name.

Slug was the internal name; "name" is what users see in Discord command
parameters and the admin panel.

Revision ID: d71b13e08cba
Revises: e7c979f86441
Create Date: 2026-05-02 22:57:00.000000+00:00
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)

revision: str = "d71b13e08cba"
down_revision: str = "e7c979f86441"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_items") as batch_op:
        try:
            batch_op.alter_column("slug", new_column_name="name")
        except OperationalError:
            log.warning("slug column rename failed (may already be name), skipping")


def downgrade() -> None:
    with op.batch_alter_table("media_items") as batch_op:
        try:
            batch_op.alter_column("name", new_column_name="slug")
        except OperationalError:
            log.warning("name column rename failed, skipping")
