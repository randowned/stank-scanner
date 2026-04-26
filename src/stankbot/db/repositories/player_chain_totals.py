"""player_chain_totals repository — write-through cache for per-chain stank/reaction counts.

The ``player_chain_totals`` table mirrors:
- COUNT(SP_BASE) FROM events GROUP BY guild_id, user_id, chain_id
- COUNT(SP_REACTION) FROM events GROUP BY guild_id, user_id, chain_id

Writes happen inside ``events_repo.append()`` so the cache never drifts.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Event, EventType, PlayerChainTotal


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def upsert(
    session: AsyncSession,
    *,
    guild_id: int,
    user_id: int,
    chain_id: int,
    stanks_delta: int = 0,
    reactions_delta: int = 0,
) -> None:
    """Add counter deltas to the chain row (idempotent)."""
    now = datetime.now(tz=UTC)
    row = await session.get(PlayerChainTotal, (guild_id, user_id, chain_id))
    if row is None:
        row = PlayerChainTotal(
            guild_id=guild_id,
            user_id=user_id,
            chain_id=chain_id,
            stanks_in_chain=max(stanks_delta, 0),
            reactions_in_chain=max(reactions_delta, 0),
            updated_at=now,
        )
        session.add(row)
    else:
        row.stanks_in_chain += stanks_delta
        row.reactions_in_chain += reactions_delta
        row.updated_at = now
    await session.flush()


async def get(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    chain_id: int,
) -> PlayerChainTotal | None:
    """Return the chain totals for a specific user, or None if not found."""
    return await session.get(PlayerChainTotal, (guild_id, user_id, chain_id))


async def get_for_user(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
) -> dict[int, PlayerChainTotal]:
    """Return all chain totals for a user, keyed by chain_id."""
    stmt = (
        select(PlayerChainTotal)
        .where(
            PlayerChainTotal.guild_id == guild_id,
            PlayerChainTotal.user_id == user_id,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {r.chain_id: r for r in rows}


async def get_for_chain(
    session: AsyncSession,
    guild_id: int,
    chain_id: int,
) -> dict[int, PlayerChainTotal]:
    """Return all user totals for a chain, keyed by user_id."""
    stmt = (
        select(PlayerChainTotal)
        .where(
            PlayerChainTotal.guild_id == guild_id,
            PlayerChainTotal.chain_id == chain_id,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {r.user_id: r for r in rows}


# ---------------------------------------------------------------------------
# Rebuild (called from admin rebuild)
# ---------------------------------------------------------------------------


async def rebuild(session: AsyncSession, guild_id: int) -> int:
    """Truncate all rows for ``guild_id`` and repopulate from events.

    Returns the number of rows inserted.
    """
    await session.execute(
        delete(PlayerChainTotal).where(PlayerChainTotal.guild_id == guild_id)
    )

    # Count stanks per (guild_id, user_id, chain_id)
    stanks_stmt = (
        select(
            Event.guild_id,
            Event.user_id,
            Event.chain_id,
            func.count(Event.id).label("stanks"),
        )
        .where(
            Event.guild_id == guild_id,
            Event.type == EventType.SP_BASE,
            Event.chain_id.is_not(None),
            Event.user_id.is_not(None),
        )
        .group_by(Event.guild_id, Event.user_id, Event.chain_id)
    )
    stanks_rows = (await session.execute(stanks_stmt)).all()

    # Count reactions per (guild_id, user_id, chain_id)
    reactions_stmt = (
        select(
            Event.guild_id,
            Event.user_id,
            Event.chain_id,
            func.count(Event.id).label("reactions"),
        )
        .where(
            Event.guild_id == guild_id,
            Event.type == EventType.SP_REACTION,
            Event.chain_id.is_not(None),
            Event.user_id.is_not(None),
        )
        .group_by(Event.guild_id, Event.user_id, Event.chain_id)
    )
    reactions_rows = (await session.execute(reactions_stmt)).all()

    # Build lookup dicts
    stanks_map: dict[tuple[int, int, int], int] = {}
    for gid, uid, cid, cnt in stanks_rows:
        key = (int(gid), int(uid), int(cid))
        stanks_map[key] = int(cnt or 0)

    reactions_map: dict[tuple[int, int, int], int] = {}
    for gid, uid, cid, cnt in reactions_rows:
        key = (int(gid), int(uid), int(cid))
        reactions_map[key] = int(cnt or 0)

    # Merge into PlayerChainTotal rows
    now = datetime.now(tz=UTC)
    all_keys = set(stanks_map.keys()) | set(reactions_map.keys())
    count = 0
    for gid, uid, cid in all_keys:
        session.add(
            PlayerChainTotal(
                guild_id=gid,
                user_id=uid,
                chain_id=cid,
                stanks_in_chain=stanks_map.get((gid, uid, cid), 0),
                reactions_in_chain=reactions_map.get((gid, uid, cid), 0),
                updated_at=now,
            )
        )
        count += 1

    await session.flush()
    return count


async def delete_for_chain(session: AsyncSession, guild_id: int, chain_id: int) -> None:
    """Delete all totals for a specific chain."""
    await session.execute(
        delete(PlayerChainTotal).where(
            PlayerChainTotal.guild_id == guild_id,
            PlayerChainTotal.chain_id == chain_id,
        )
    )
    await session.flush()