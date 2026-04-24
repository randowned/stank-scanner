"""Reaction anti-cheat ledger.

A row in ``reaction_awards`` is a permanent claim: "we awarded SP for
(message_id, user_id, sticker_id)". Rows are NEVER deleted, even when the
user removes the reaction in Discord. Re-adding the reaction cannot
trigger a second award because the PK already exists.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Event, EventType, ReactionAward


async def try_claim(
    session: AsyncSession,
    *,
    guild_id: int,
    message_id: int,
    user_id: int,
    sticker_id: int,
    chain_id: int | None = None,
) -> bool:
    """Attempt to claim the reaction award. Returns ``True`` if this is
    the first claim (caller should emit the SP event); ``False`` if the
    claim already exists (caller must NOT re-award).
    """
    existing = await session.get(ReactionAward, (message_id, user_id, sticker_id))
    if existing is not None:
        return False
    session.add(
        ReactionAward(
            message_id=message_id,
            user_id=user_id,
            sticker_id=sticker_id,
            guild_id=guild_id,
            chain_id=chain_id,
        )
    )
    return True


async def count_for_chain(
    session: AsyncSession, *, guild_id: int, chain_id: int
) -> int:
    """Total reaction awards in a single chain, via SP_REACTION events."""
    stmt = select(func.count()).where(
        Event.guild_id == guild_id,
        Event.type == EventType.SP_REACTION,
        Event.chain_id == chain_id,
    )
    result = await session.scalar(stmt)
    return int(result or 0)


async def count_per_user_for_chain(
    session: AsyncSession, *, guild_id: int, chain_id: int
) -> dict[int, int]:
    """Per-user reaction award counts in a chain, via SP_REACTION events."""
    stmt = (
        select(Event.user_id, func.count())
        .where(
            Event.guild_id == guild_id,
            Event.type == EventType.SP_REACTION,
            Event.chain_id == chain_id,
        )
        .group_by(Event.user_id)
    )
    result = await session.execute(stmt)
    return {int(uid): int(n) for uid, n in result.all() if uid is not None}


async def count_for_session(
    session: AsyncSession, *, guild_id: int, session_id: int | None
) -> int:
    """Total reaction-award events in a session (SP_REACTION event rows)."""
    stmt = select(func.count()).where(
        Event.guild_id == guild_id,
        Event.type == EventType.SP_REACTION,
        Event.session_id == session_id,
    )
    result = await session.scalar(stmt)
    return int(result or 0)


async def count_per_user_for_session(
    session: AsyncSession, *, guild_id: int, session_id: int | None
) -> dict[int, int]:
    """Per-user reaction-award counts in a session, keyed by user_id."""
    stmt = (
        select(Event.user_id, func.count())
        .where(
            Event.guild_id == guild_id,
            Event.type == EventType.SP_REACTION,
            Event.session_id == session_id,
        )
        .group_by(Event.user_id)
    )
    result = await session.execute(stmt)
    return {int(uid): int(n) for uid, n in result.all() if uid is not None}
