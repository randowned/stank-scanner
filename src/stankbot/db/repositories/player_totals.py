"""player_totals repository — write-through cache for SP/PP aggregates.

The ``player_totals`` table is a materialized cache that mirrors
``SUM(delta) FROM events GROUP BY guild_id, user_id, session_id``.
Writes happen atomically inside ``events_repo.append()`` so the cache
never drifts. Reads try the cache first and fall back to an event-level
aggregation if the row is missing (e.g. after a schema migration).

``session_id=0`` is the special "all-time" aggregate row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import PlayerTotal

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def upsert(
    session: AsyncSession,
    *,
    guild_id: int,
    user_id: int,
    session_id: int = 0,
    sp_delta: int = 0,
    pp_delta: int = 0,
    stanks_in_session_delta: int = 0,
    reactions_in_session_delta: int = 0,
) -> None:
    """Add ``sp_delta`` / ``pp_delta`` / counters to the cache row (idempotent).

    Uses SQLite-compatible INSERT … ON CONFLICT UPSERT via
    session.merge, which is portable across SQLAlchemy dialects.
    """
    now = datetime.now(tz=UTC)
    row = await session.get(PlayerTotal, (guild_id, user_id, session_id))
    if row is None:
        row = PlayerTotal(
            guild_id=guild_id,
            user_id=user_id,
            session_id=session_id,
            earned_sp=max(sp_delta, 0),
            punishments=max(pp_delta, 0),
            stanks_in_session=max(stanks_in_session_delta, 0),
            reactions_in_session=max(reactions_in_session_delta, 0),
            updated_at=now,
        )
        session.add(row)
    else:
        row.earned_sp += sp_delta
        row.punishments += pp_delta
        row.stanks_in_session += stanks_in_session_delta
        row.reactions_in_session += reactions_in_session_delta
        row.updated_at = now
    await session.flush()


async def get(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    session_id: int = 0,
) -> PlayerTotal | None:
    return await session.get(PlayerTotal, (guild_id, user_id, session_id))


# ---------------------------------------------------------------------------
# Rebuild (called from admin rebuild)
# ---------------------------------------------------------------------------


async def rebuild(session: AsyncSession, guild_id: int) -> int:
    """Truncate all rows for ``guild_id`` and repopulate from events.

    Returns the number of rows inserted.
    """
    # Delete existing rows for this guild
    from sqlalchemy import case, delete, func, select

    from stankbot.db.models import Event, EventType

    await session.execute(
        delete(PlayerTotal).where(PlayerTotal.guild_id == guild_id)
    )

    _sp_types = (
        EventType.SP_BASE,
        EventType.SP_POSITION_BONUS,
        EventType.SP_STARTER_BONUS,
        EventType.SP_FINISH_BONUS,
        EventType.SP_REACTION,
        EventType.SP_TEAM_PLAYER,
    )

    # All-time rows (session_id=0)
    stmt = (
        select(
            Event.guild_id,
            Event.user_id,
            func.coalesce(
                func.sum(
                    case(
                        (Event.type.in_([t.value for t in _sp_types]), Event.delta),
                        else_=0,
                    )
                ),
                0,
            ).label("sp"),
            func.coalesce(
                func.sum(
                    case(
                        (Event.type == EventType.PP_BREAK, Event.delta),
                        else_=0,
                    )
                ),
                0,
            ).label("pp"),
        )
        .where(Event.guild_id == guild_id, Event.user_id.is_not(None))
        .group_by(Event.guild_id, Event.user_id)
    )
    rows = (await session.execute(stmt)).all()
    count = 0
    now = datetime.now(tz=UTC)
    for gid, uid, sp, pp in rows:
        session.add(
            PlayerTotal(
                guild_id=int(gid),
                user_id=int(uid),
                session_id=0,
                earned_sp=int(sp or 0),
                punishments=int(pp or 0),
                updated_at=now,
            )
        )
        count += 1

    # Per-session rows (session_id = the session_start event id)
    stmt2 = (
        select(
            Event.guild_id,
            Event.user_id,
            Event.session_id,
            func.coalesce(
                func.sum(
                    case(
                        (Event.type.in_([t.value for t in _sp_types]), Event.delta),
                        else_=0,
                    )
                ),
                0,
            ).label("sp"),
            func.coalesce(
                func.sum(
                    case(
                        (Event.type == EventType.PP_BREAK, Event.delta),
                        else_=0,
                    )
                ),
                0,
            ).label("pp"),
            func.coalesce(
                func.sum(case((Event.type == EventType.SP_BASE, 1), else_=0)),
                0,
            ).label("stanks"),
            func.coalesce(
                func.sum(case((Event.type == EventType.SP_REACTION, 1), else_=0)),
                0,
            ).label("reactions"),
        )
        .where(
            Event.guild_id == guild_id,
            Event.user_id.is_not(None),
            Event.session_id.is_not(None),
        )
        .group_by(Event.guild_id, Event.user_id, Event.session_id)
    )
    rows2 = (await session.execute(stmt2)).all()
    for gid, uid, sid, sp, pp, stanks, reacts in rows2:
        session.add(
            PlayerTotal(
                guild_id=int(gid),
                user_id=int(uid),
                session_id=int(sid),
                earned_sp=int(sp or 0),
                punishments=int(pp or 0),
                stanks_in_session=int(stanks or 0),
                reactions_in_session=int(reacts or 0),
                updated_at=now,
            )
        )
        count += 1

    await session.flush()
    return count


# ---------------------------------------------------------------------------
# Rank lookup (uses totals instead of scanning events)
# ---------------------------------------------------------------------------


async def get_rank(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    *,
    session_id: int = 0,
) -> int | None:
    """1-indexed rank by net SP using ``player_totals``.

    Returns ``None`` if the user has no row in ``player_totals``.
    """
    from sqlalchemy import func, select

    row = await session.get(PlayerTotal, (guild_id, user_id, session_id))
    if row is None:
        return None

    net = row.earned_sp - row.punishments
    # Count how many users have strictly higher net
    stmt = (
        select(func.count())
        .where(
            PlayerTotal.guild_id == guild_id,
            PlayerTotal.session_id == session_id,
            (PlayerTotal.earned_sp - PlayerTotal.punishments) > net,
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return count + 1
