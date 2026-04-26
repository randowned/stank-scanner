"""History queries — derive session/chain/user summaries from the event log.

Every summary is computed on demand by filtering ``events`` between a pair
of ``session_start``/``session_end`` markers (for session summaries) or
by grouping on ``chain_id`` / ``user_id``. No snapshot tables — see the
"sessions-from-events" principle in the approved plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Chain, Event, EventType
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import players as players_repo

if TYPE_CHECKING:
    pass


@dataclass(slots=True)
class UserSummary:
    user_id: int
    display_name: str
    earned_sp: int
    punishments: int
    chains_started: int
    chains_broken: int
    last_stank_at: datetime | None


@dataclass(slots=True)
class UserSummaryBoth:
    session: UserSummary
    alltime: UserSummary


@dataclass(slots=True)
class ChainSummary:
    chain_id: int
    guild_id: int
    session_id: int | None
    started_at: datetime
    broken_at: datetime | None
    length: int
    unique_contributors: int
    starter_user_id: int
    broken_by_user_id: int | None
    contributors: list[tuple[int, int]]  # (user_id, stanks_in_chain)


@dataclass(slots=True)
class SessionSummary:
    session_id: int
    guild_id: int
    started_at: datetime | None
    ended_at: datetime | None
    chains_started: int
    chains_broken: int
    top_earner: tuple[int, int] | None  # (user_id, sp)
    top_breaker: tuple[int, int] | None  # (user_id, pp)


async def user_summary(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    *,
    session_id: int | None = None,
) -> UserSummary:
    sp, pp = await events_repo.sp_pp_totals(
        session, guild_id, user_id, session_id=session_id
    )
    started = await events_repo.chains_started(session, guild_id, user_id, session_id=session_id)
    broken = await events_repo.chains_broken(session, guild_id, user_id, session_id=session_id)
    last = await events_repo.last_stank_at(session, guild_id, user_id)
    player = await players_repo.get(session, guild_id, user_id)
    name = player.display_name if player else str(user_id)
    return UserSummary(
        user_id=user_id,
        display_name=name,
        earned_sp=sp,
        punishments=pp,
        chains_started=started,
        chains_broken=broken,
        last_stank_at=last,
    )


async def user_summary_both(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    current_session_id: int | None,
) -> UserSummaryBoth:
    alltime = await user_summary(session, guild_id, user_id, session_id=None)
    if current_session_id is not None:
        session_summary = await user_summary(
            session, guild_id, user_id, session_id=current_session_id
        )
    else:
        session_summary = UserSummary(
            user_id=user_id,
            display_name=alltime.display_name,
            earned_sp=0,
            punishments=0,
            chains_started=0,
            chains_broken=0,
            last_stank_at=None,
        )
    return UserSummaryBoth(session=session_summary, alltime=alltime)


async def chain_summary(
    session: AsyncSession, guild_id: int, chain_id: int
) -> ChainSummary | None:
    chain = await session.get(Chain, chain_id)
    if chain is None or chain.guild_id != guild_id:
        return None

    from stankbot.db.repositories import chains as chains_repo

    length, unique = await chains_repo.chain_length_and_unique(session, chain_id)
    contributors = await chains_repo.contributors(session, chain_id)

    counts: dict[int, int] = {}
    for uid in contributors:
        counts[uid] = counts.get(uid, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)

    return ChainSummary(
        chain_id=chain.id,
        guild_id=chain.guild_id,
        session_id=chain.session_id,
        started_at=chain.started_at,
        broken_at=chain.broken_at,
        length=length,
        unique_contributors=unique,
        starter_user_id=chain.starter_user_id,
        broken_by_user_id=chain.broken_by_user_id,
        contributors=ordered,
    )


async def session_summary(
    session: AsyncSession, guild_id: int, session_id: int
) -> SessionSummary | None:
    # SESSION_START event has session_id=NULL (it IS the session anchor), so
    # events_in_session never returns it. Always fetch it directly for started_at.
    start_row = await session.get(Event, session_id)
    if start_row is None or start_row.guild_id != guild_id:
        return None

    events = await events_repo.events_in_session(session, guild_id, session_id)
    if not events:
        return SessionSummary(
            session_id=session_id,
            guild_id=guild_id,
            started_at=start_row.created_at,
            ended_at=None,
            chains_started=0,
            chains_broken=0,
            top_earner=None,
            top_breaker=None,
        )

    started_at: datetime | None = start_row.created_at
    ended_at: datetime | None = None
    chains_started = 0
    chains_broken = 0
    for ev in events:
        if ev.type == EventType.SESSION_END:
            ended_at = ev.created_at
        elif ev.type == EventType.CHAIN_START:
            chains_started += 1
        elif ev.type == EventType.CHAIN_BREAK:
            chains_broken += 1

    sp_types = [
        EventType.SP_BASE,
        EventType.SP_POSITION_BONUS,
        EventType.SP_STARTER_BONUS,
        EventType.SP_FINISH_BONUS,
        EventType.SP_REACTION,
    ]
    sp_stmt = (
        select(Event.user_id, func.sum(Event.delta).label("sp"))
        .where(
            Event.guild_id == guild_id,
            Event.session_id == session_id,
            Event.user_id.is_not(None),
            Event.type.in_([t.value for t in sp_types]),
        )
        .group_by(Event.user_id)
        .order_by(func.sum(Event.delta).desc())
        .limit(1)
    )
    pp_stmt = (
        select(Event.user_id, func.sum(Event.delta).label("pp"))
        .where(
            Event.guild_id == guild_id,
            Event.session_id == session_id,
            Event.user_id.is_not(None),
            Event.type == EventType.PP_BREAK,
        )
        .group_by(Event.user_id)
        .order_by(func.sum(Event.delta).desc())
        .limit(1)
    )
    sp_row = (await session.execute(sp_stmt)).first()
    pp_row = (await session.execute(pp_stmt)).first()

    return SessionSummary(
        session_id=session_id,
        guild_id=guild_id,
        started_at=started_at,
        ended_at=ended_at,
        chains_started=chains_started,
        chains_broken=chains_broken,
        top_earner=(int(sp_row[0]), int(sp_row[1] or 0)) if sp_row else None,
        top_breaker=(int(pp_row[0]), int(pp_row[1] or 0)) if pp_row else None,
    )
