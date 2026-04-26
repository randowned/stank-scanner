"""Event-log repository.

The event log is the source of truth for SP/PP totals, session boundaries,
chain state, and achievement evaluation. Every derivable table (records,
player_totals) is regenerable by replaying events through the scoring +
session services — so every mutation MUST go through ``append``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Event, EventType


async def append(
    session: AsyncSession,
    *,
    guild_id: int,
    type: EventType | str,
    delta: int = 0,
    user_id: int | None = None,
    altar_id: int | None = None,
    session_id: int | None = None,
    chain_id: int | None = None,
    message_id: int | None = None,
    reason: str | None = None,
    custom_event_key: str | None = None,
    payload: dict[str, Any] | list[Any] | None = None,
    created_at: datetime | None = None,
) -> Event:
    """Insert an event row and flush so the caller sees the generated id.

    Commit is the caller's responsibility (``session_scope`` handles it).
    """
    event = Event(
        guild_id=guild_id,
        type=str(type),
        delta=delta,
        user_id=user_id,
        altar_id=altar_id,
        session_id=session_id,
        chain_id=chain_id,
        message_id=message_id,
        reason=reason,
        custom_event_key=custom_event_key,
        payload_json=payload,
    )
    if created_at is not None:
        event.created_at = created_at
    session.add(event)
    await session.flush()

    # Write-through to player_totals cache (same transaction).
    if event.delta != 0 and event.user_id is not None:
        from stankbot.db.repositories import player_totals as pt_repo

        sp_delta = event.delta if str(event.type) in {t.value for t in _SP_TYPES} else 0
        pp_delta = event.delta if str(event.type) == EventType.PP_BREAK else 0
        stanks_delta = 1 if str(event.type) == EventType.SP_BASE else 0
        reactions_delta = 1 if str(event.type) == EventType.SP_REACTION else 0

        await pt_repo.upsert(
            session,
            guild_id=event.guild_id,
            user_id=event.user_id,
            session_id=0,  # all-time
            sp_delta=sp_delta,
            pp_delta=pp_delta,
        )
        if event.session_id is not None:
            await pt_repo.upsert(
                session,
                guild_id=event.guild_id,
                user_id=event.user_id,
                session_id=event.session_id,
                sp_delta=sp_delta,
                pp_delta=pp_delta,
                stanks_in_session_delta=stanks_delta,
                reactions_in_session_delta=reactions_delta,
            )

    # Write-through to player_chain_totals cache.
    if event.user_id is not None and event.chain_id is not None:
        from stankbot.db.repositories import player_chain_totals as pct_repo

        stanks_delta = 1 if str(event.type) == EventType.SP_BASE else 0
        reactions_delta = 1 if str(event.type) == EventType.SP_REACTION else 0

        if stanks_delta or reactions_delta:
            await pct_repo.upsert(
                session,
                guild_id=event.guild_id,
                user_id=event.user_id,
                chain_id=event.chain_id,
                stanks_delta=stanks_delta,
                reactions_delta=reactions_delta,
            )

    # Broadcast live event via WebSocket (fire-and-forget, gated by active connections).
    try:
        from stankbot.web.ws import broadcast_game_event, has_active_connections
        if has_active_connections(guild_id):
            _user_name: str | None = None
            if user_id is not None:
                from stankbot.db.models import Player
                player = await session.get(Player, (guild_id, user_id))
                _user_name = player.display_name if player else None
            asyncio.create_task(
                broadcast_game_event(
                    guild_id,
                    event_id=event.id,
                    event_type=event.type,
                    user_id=user_id,
                    user_name=_user_name,
                    delta=event.delta,
                    reason=event.reason,
                    created_at=event.created_at.isoformat() if event.created_at else None,
                )
            )
    except Exception:
        pass  # WS not available (tests, CLI mode, import error)

    return event


async def latest_session_start_id(session: AsyncSession, guild_id: int) -> int | None:
    """Return the ``id`` of the most recent ``session_start`` event, or
    ``None`` if no sessions have ever started for this guild.
    """
    stmt = (
        select(Event.id)
        .where(Event.guild_id == guild_id, Event.type == EventType.SESSION_START)
        .order_by(Event.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def session_event_ids(session: AsyncSession, guild_id: int) -> list[int]:
    """All ``session_start`` event ids for a guild, ordered oldest-first.
    Used to enumerate sessions in history queries.
    """
    stmt = (
        select(Event.id)
        .where(Event.guild_id == guild_id, Event.type == EventType.SESSION_START)
        .order_by(Event.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def session_ids_where_user_has_sp(
    session: AsyncSession, guild_id: int, user_id: int
) -> list[int]:
    """Return session_ids where ``user_id`` has at least one SP event,
    ordered by session_id ASC. Used by ``_streaker`` for efficient
    consecutive-session checks.
    """
    stmt = (
        select(Event.session_id)
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
            Event.type.in_([t.value for t in _SP_TYPES]),
            Event.session_id.is_not(None),
        )
        .group_by(Event.session_id)
        .having(func.sum(Event.delta) > 0)
        .order_by(Event.session_id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_session_starts(session: AsyncSession, guild_id: int, *, up_to_id: int) -> int:
    """Return how many SESSION_START events exist for the guild with id <= up_to_id.

    Used to convert raw event IDs into sequential session numbers.
    """
    stmt = select(func.count()).where(
        Event.guild_id == guild_id,
        Event.type == EventType.SESSION_START,
        Event.id <= up_to_id,
    )
    return (await session.execute(stmt)).scalar_one()


async def sp_pp_totals(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    *,
    session_id: int | None = None,
) -> tuple[int, int]:
    """Return ``(earned_sp, punishments)`` for one user.

    If ``session_id`` is given, only events within that session are summed.
    Tries the ``player_totals`` cache first; falls back to an event-level
    aggregation if the cache row is missing.
    """
    from stankbot.db.repositories import player_totals as pt_repo

    sid = session_id or 0
    cached = await pt_repo.get(session, guild_id, user_id, sid)
    if cached is not None:
        return cached.earned_sp, cached.punishments

    # Cache miss — derive from events (e.g. after migration).
    where = [Event.guild_id == guild_id, Event.user_id == user_id]
    if session_id is not None:
        where.append(Event.session_id == session_id)

    stmt = select(
        func.coalesce(
            func.sum(
                case(
                    (Event.type.in_([t.value for t in _SP_TYPES]), Event.delta),
                    else_=0,
                )
            ),
            0,
        ).label("sp"),
        func.coalesce(
            func.sum(
                case((Event.type == EventType.PP_BREAK, Event.delta), else_=0)
            ),
            0,
        ).label("pp"),
    ).where(*where)
    row = (await session.execute(stmt)).one()
    return int(row.sp), int(row.pp)


async def events_in_session(
    session: AsyncSession, guild_id: int, session_id: int
) -> Sequence[Event]:
    stmt = (
        select(Event)
        .where(Event.guild_id == guild_id, Event.session_id == session_id)
        .order_by(Event.id.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def events_for_chain(session: AsyncSession, guild_id: int, chain_id: int) -> Sequence[Event]:
    stmt = (
        select(Event)
        .where(Event.guild_id == guild_id, Event.chain_id == chain_id)
        .order_by(Event.id.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def wipe_guild_events(session: AsyncSession, guild_id: int) -> None:
    """Destructive — used by ``/stank-admin rebuild-from-history``."""
    await session.execute(Event.__table__.delete().where(Event.guild_id == guild_id))


_SP_TYPES = (
    EventType.SP_BASE,
    EventType.SP_POSITION_BONUS,
    EventType.SP_STARTER_BONUS,
    EventType.SP_FINISH_BONUS,
    EventType.SP_REACTION,
    EventType.SP_TEAM_PLAYER,
)


async def count_sp_base_per_user_for_session(
    session: AsyncSession,
    guild_id: int,
    session_id: int,
    user_ids: list[int] | None = None,
) -> dict[int, int]:
    """Return ``{user_id: stank_count}`` for SP_BASE events in the given session."""
    stmt = (
        select(Event.user_id, func.count(Event.id).label("cnt"))
        .where(
            Event.guild_id == guild_id,
            Event.session_id == session_id,
            Event.type == EventType.SP_BASE,
            Event.user_id.is_not(None),
        )
    )
    if user_ids:
        stmt = stmt.where(Event.user_id.in_(user_ids))
    stmt = stmt.group_by(Event.user_id)
    rows = (await session.execute(stmt)).all()
    return {int(uid): int(cnt) for uid, cnt in rows}


async def count_sp_base_per_user_for_chain(
    session: AsyncSession,
    guild_id: int,
    chain_id: int,
    user_ids: list[int] | None = None,
) -> dict[int, int]:
    """Return ``{user_id: stank_count}`` for SP_BASE events in the given chain."""
    stmt = (
        select(Event.user_id, func.count(Event.id).label("cnt"))
        .where(
            Event.guild_id == guild_id,
            Event.chain_id == chain_id,
            Event.type == EventType.SP_BASE,
            Event.user_id.is_not(None),
        )
    )
    if user_ids:
        stmt = stmt.where(Event.user_id.in_(user_ids))
    stmt = stmt.group_by(Event.user_id)
    rows = (await session.execute(stmt)).all()
    return {int(uid): int(cnt) for uid, cnt in rows}


async def leaderboard(
    session: AsyncSession,
    guild_id: int,
    *,
    session_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[int, int, int]]:
    """Return ``[(user_id, earned_sp, punishments), ...]`` sorted by net SP
    descending. Uses ``player_totals`` cache.
    """
    from stankbot.db.models import PlayerTotal

    sid = session_id or 0
    stmt = (
        select(
            PlayerTotal.user_id,
            PlayerTotal.earned_sp.label("earned_sp"),
            PlayerTotal.punishments.label("punishments"),
        )
        .where(PlayerTotal.guild_id == guild_id, PlayerTotal.session_id == sid)
        .order_by((PlayerTotal.earned_sp - PlayerTotal.punishments).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(int(uid), int(sp or 0), int(pp or 0)) for uid, sp, pp in rows]


async def leaderboard_for_chain(
    session: AsyncSession,
    guild_id: int,
    chain_id: int,
) -> list[tuple[int, int, int]]:
    """Return ``[(user_id, earned_sp, punishments), ...]`` for a single chain,
    sorted by net SP descending.
    """
    sp_expr = func.sum(
        case((Event.type.in_([t.value for t in _SP_TYPES]), Event.delta), else_=0)
    ).label("earned_sp")
    pp_expr = func.sum(case((Event.type == EventType.PP_BREAK, Event.delta), else_=0)).label(
        "punishments"
    )
    stmt = (
        select(Event.user_id, sp_expr, pp_expr)
        .where(Event.guild_id == guild_id, Event.chain_id == chain_id, Event.user_id.is_not(None))
        .group_by(Event.user_id)
        .order_by((sp_expr - pp_expr).desc())
    )
    rows = (await session.execute(stmt)).all()
    return [(int(uid), int(sp or 0), int(pp or 0)) for uid, sp, pp in rows]


async def top_pp_user(session: AsyncSession, guild_id: int) -> tuple[int, int] | None:
    """All-time PP leader — the "chainbreaker". Returns
    ``(user_id, punishments)`` or ``None`` if no one has any PP yet.
    """
    pp_expr = func.coalesce(func.sum(Event.delta), 0).label("pp")
    stmt = (
        select(Event.user_id, pp_expr)
        .where(
            Event.guild_id == guild_id,
            Event.user_id.is_not(None),
            Event.type == EventType.PP_BREAK,
        )
        .group_by(Event.user_id)
        .order_by(pp_expr.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None or not row[1]:
        return None
    return int(row[0]), int(row[1])


async def user_rank(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    *,
    session_id: int | None = None,
) -> int | None:
    """1-indexed rank by net SP, or ``None`` if the user has no events.

    Uses ``player_totals`` cache — O(1) lookup instead of scanning events.
    """
    from stankbot.db.repositories import player_totals as pt_repo

    return await pt_repo.get_rank(
        session, guild_id, user_id, session_id=session_id or 0
    )


async def chains_started(
    session: AsyncSession, guild_id: int, user_id: int, *, session_id: int | None = None
) -> int:
    where = [
        Event.guild_id == guild_id,
        Event.user_id == user_id,
        Event.type == EventType.CHAIN_START,
    ]
    if session_id is not None:
        where.append(Event.session_id == session_id)
    stmt = select(func.count(Event.id)).where(*where)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def chains_broken(
    session: AsyncSession, guild_id: int, user_id: int, *, session_id: int | None = None
) -> int:
    where = [
        Event.guild_id == guild_id,
        Event.user_id == user_id,
        Event.type == EventType.CHAIN_BREAK,
    ]
    if session_id is not None:
        where.append(Event.session_id == session_id)
    stmt = select(func.count(Event.id)).where(*where)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def session_participants(session: AsyncSession, guild_id: int, session_id: int) -> list[int]:
    """Distinct user_ids that earned SP or took PP within the given session."""
    scoring_types = [*(t.value for t in _SP_TYPES), EventType.PP_BREAK.value]
    stmt = (
        select(Event.user_id)
        .where(
            Event.guild_id == guild_id,
            Event.session_id == session_id,
            Event.user_id.is_not(None),
            Event.type.in_(scoring_types),
        )
        .distinct()
    )
    return [int(uid) for uid in (await session.execute(stmt)).scalars().all() if uid]


async def previous_ended_session_id(
    session: AsyncSession, guild_id: int, *, before_id: int
) -> int | None:
    """Most recent ended session_id for the guild that is older than ``before_id``.

    A session is considered ended when a SESSION_END event exists for it.
    """
    stmt = (
        select(Event.session_id)
        .where(
            Event.guild_id == guild_id,
            Event.type == EventType.SESSION_END,
            Event.session_id.is_not(None),
            Event.session_id < before_id,
        )
        .order_by(Event.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def last_sp_base_in_session(
    session: AsyncSession,
    guild_id: int,
    *,
    altar_id: int,
    session_id: int,
) -> tuple[int, int | None] | None:
    """``(user_id, chain_id)`` of the last SP_BASE event in a session for a
    given altar, or ``None`` if no SP_BASE was recorded there.
    """
    stmt = (
        select(Event.user_id, Event.chain_id)
        .where(
            Event.guild_id == guild_id,
            Event.altar_id == altar_id,
            Event.session_id == session_id,
            Event.type == EventType.SP_BASE,
        )
        .order_by(Event.id.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None or row[0] is None:
        return None
    return int(row[0]), (int(row[1]) if row[1] is not None else None)


async def count_sp_base_in_session(
    session: AsyncSession,
    guild_id: int,
    *,
    altar_id: int,
    session_id: int,
) -> int:
    """Count SP_BASE events for a (guild, altar, session)."""
    stmt = select(func.count(Event.id)).where(
        Event.guild_id == guild_id,
        Event.altar_id == altar_id,
        Event.session_id == session_id,
        Event.type == EventType.SP_BASE,
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def last_stank_at(session: AsyncSession, guild_id: int, user_id: int) -> datetime | None:
    stmt = (
        select(Event.created_at)
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
            Event.type == EventType.SP_BASE,
        )
        .order_by(Event.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
