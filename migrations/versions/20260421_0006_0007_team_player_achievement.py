"""Seed the Team Player achievement.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-21 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_achievements = sa.table(
    "achievements",
    sa.column("key", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
    sa.column("icon", sa.String()),
    sa.column("rule_json", sa.JSON()),
    sa.column("is_global", sa.Boolean()),
)


_ROW = {
    "key": "team_player",
    "name": "Team Player",
    "description": "Last stank of one shift, first stank of the next.",
    "icon": "🤝",
    "rule_json": {"impl": "code", "key": "team_player"},
    "is_global": True,
}


def upgrade() -> None:
    op.bulk_insert(_achievements, [_ROW])


def downgrade() -> None:
    op.execute(
        _achievements.delete().where(_achievements.c.key == "team_player")
    )
