"""Replace (guild_id, slug) unique constraint with (guild_id, media_type, slug).

Slugs must be unique per media-type within a guild, not globally.
This allows the same slug to be used for a YouTube video and a Spotify
track in the same guild — commands already use provider-scoped
parameters (``/stats youtube info name:{slug}``) so there is no
ambiguity.

Revision ID: e7c979f86441
Revises: add_media_slug
Create Date: 2026-05-02 20:36:54.359361+00:00
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)

revision: str = "e7c979f86441"
down_revision: str = "add_media_slug"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_items") as batch_op:
        try:
            batch_op.drop_constraint("uq_media_slug", type_="unique")
        except OperationalError:
            log.warning("uq_media_slug constraint not found, skipping drop")

        try:
            batch_op.create_unique_constraint(
                "uq_media_slug", ["guild_id", "media_type", "slug"]
            )
        except OperationalError:
            log.warning("new uq_media_slug constraint already exists, skipping")


def downgrade() -> None:
    with op.batch_alter_table("media_items") as batch_op:
        try:
            batch_op.drop_constraint("uq_media_slug", type_="unique")
        except OperationalError:
            log.warning("uq_media_slug constraint not found, skipping drop")

        try:
            batch_op.create_unique_constraint(
                "uq_media_slug", ["guild_id", "slug"]
            )
        except OperationalError:
            log.warning("old uq_media_slug constraint already exists, skipping")
