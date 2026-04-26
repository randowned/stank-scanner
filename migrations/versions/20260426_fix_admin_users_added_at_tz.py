"""fix_admin_users_added_at_tz

Revision ID: c0d3f4e5a6b7
Revises: b1a2c3d4e5f6
Create Date: 2026-04-26 00:00:00.000000+00:00

Fix the admin_users.added_at column to use TIMESTAMP WITH TIME ZONE on PostgreSQL.
The previous migration (a99d29835488) recreated the table using raw SQL with
TIMESTAMP (without timezone), which is incorrect. This migration fixes
the column type on PostgreSQL while being a no-op on SQLite.

The model already declares DateTime(timezone=True), but the raw SQL in the
old migration created TIMESTAMP WITHOUT TIME ZONE.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c0d3f4e5a6b7'
down_revision: str | Sequence[str] | None = 'b1a2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == 'postgresql':
        # On PostgreSQL, alter the column to be TIMESTAMP WITH TIME ZONE
        conn.exec_driver_sql(
            "ALTER TABLE admin_users ALTER COLUMN added_at TYPE TIMESTAMP WITH TIME ZONE"
        )
    # On SQLite, this is a no-op since SQLite is typeless


def downgrade() -> None:
    # No downgrade - this is a corrective migration
    pass