"""Per-(guild, altar, user) cooldown tracker."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Cooldown


def _as_utc(value: datetime | None) -> datetime | None:
    # SQLite's ``DateTime(timezone=True)`` round-trips as a naive datetime;
    # coerce to UTC-aware so downstream arithmetic works regardless of backend.
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def get_last_stank(
    session: AsyncSession, *, guild_id: int, altar_id: int, user_id: int
) -> datetime | None:
    row = await session.get(Cooldown, (guild_id, altar_id, user_id))
    return _as_utc(row.last_valid_stank_at) if row else None


async def set_last_stank(
    session: AsyncSession,
    *,
    guild_id: int,
    altar_id: int,
    user_id: int,
    when: datetime,
) -> None:
    row = await session.get(Cooldown, (guild_id, altar_id, user_id))
    if row is None:
        session.add(
            Cooldown(
                guild_id=guild_id,
                altar_id=altar_id,
                user_id=user_id,
                last_valid_stank_at=when,
            )
        )
    else:
        row.last_valid_stank_at = when


async def clear_for_altar(
    session: AsyncSession, *, guild_id: int, altar_id: int
) -> None:
    """Remove every cooldown row for a (guild, altar) — called on chain break."""
    await session.execute(
        delete(Cooldown).where(
            Cooldown.guild_id == guild_id, Cooldown.altar_id == altar_id
        )
    )


async def clear_for_guild(session: AsyncSession, *, guild_id: int) -> None:
    """Remove every cooldown row for a guild — called on session rollover so
    the same user can be the last stanker of one shift and first of the next.
    """
    await session.execute(delete(Cooldown).where(Cooldown.guild_id == guild_id))


def seconds_remaining(
    last_stank_at: datetime | None,
    *,
    cooldown_seconds: int,
    now: datetime,
) -> int:
    """Return seconds left on the cooldown, or 0 if the user can stank."""
    if last_stank_at is None:
        return 0
    elapsed = (now - last_stank_at).total_seconds()
    remaining = cooldown_seconds - elapsed
    return max(0, int(remaining))
