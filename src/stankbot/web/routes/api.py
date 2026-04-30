"""Public JSON API routes for the SvelteKit dashboard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.utils.time_utils import utc_isoformat
from stankbot.web.tools import (
    get_active_guild_id,
    get_db,
    require_global_admin,
    require_guild_member,
)
from stankbot.web.transport import MsgPackResponse
from stankbot.web.ws import get_board_state

router = APIRouter(prefix="")
log = logging.getLogger(__name__)


async def _compute_stank_streak(
    session: AsyncSession, guild_id: int, user_id: int
) -> dict:
    """Return ``{"current": int, "longest": int}`` bounded to last 90 days."""
    from datetime import date, timedelta

    from sqlalchemy import func, select

    from stankbot.db.models import Event, EventType

    cutoff = datetime.now(UTC) - timedelta(days=90)
    stmt = (
        select(func.date(Event.created_at))
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
            Event.type == EventType.SP_BASE,
            Event.created_at >= cutoff,
        )
        .distinct()
        .order_by(func.date(Event.created_at).desc())
        .limit(365)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return {"current": 0, "longest": 0}

    dates = sorted([d if isinstance(d, date) else date.fromisoformat(d) for d in rows])
    longest = 1
    run = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    today = datetime.now(UTC).date()
    current = run if (dates[-1] == today or dates[-1] == today - timedelta(days=1)) else 0
    return {"current": current, "longest": longest}


@router.get("/ping")
async def ping(request: Request) -> MsgPackResponse:
    return MsgPackResponse({"status": "ok"}, request)


@router.get("/api/guilds")
async def api_guilds(
    request: Request,
    user: dict = Depends(require_global_admin),
) -> MsgPackResponse:
    """Return bot guilds for global admins (guild switcher)."""
    from stankbot.web.tools import _is_owner, get_active_guild_id

    bot_guilds: list[dict] = getattr(request.app.state, "bot_guilds", [])
    active_gid = get_active_guild_id(request)

    def icon_url(guild_id: int, icon_hash: str | None) -> str | None:
        if not icon_hash:
            return None
        ext = "gif" if icon_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{ext}"

    results = []
    for g in bot_guilds:
        gid = int(g.get("id", 0))
        if gid == 0:
            continue
        results.append({
            "id": str(gid),
            "name": g.get("name", ""),
            "icon_url": icon_url(gid, g.get("icon")),
            "is_owner": _is_owner(request),
            "is_active": gid == active_gid,
        })

    results.sort(key=lambda g: (not g["is_active"], g["name"].lower()))
    return MsgPackResponse(results, request)


@router.get("/api/board")
async def api_board(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> MsgPackResponse:
    """Return board state with optional paginated rankings.

    ``offset=0``: full state (guild, chain, record, session, rankings).
    ``offset>0``: only ``rankings`` + ``has_more`` (lighter query).
    """
    from stankbot.web.tools import guild_name_for

    guild_name = await guild_name_for(session, guild_id)
    state = await get_board_state(session, guild_id, guild_name)

    if offset == 0:
        return MsgPackResponse(state, request)

    # Paginated rankings only — fetch from player_totals cache directly.
    from sqlalchemy import select

    from stankbot.db.models import PlayerChainTotal, PlayerTotal
    from stankbot.db.repositories import altars as altars_repo
    from stankbot.db.repositories import chains as chains_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.services.session_service import SessionService

    altar = await altars_repo.primary(session, guild_id)
    if altar is None:
        return MsgPackResponse({"rankings": [], "has_more": False}, request)

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)

    # Fetch rankings from player_totals cache
    stmt = (
        select(PlayerTotal)
        .where(
            PlayerTotal.guild_id == guild_id,
            PlayerTotal.session_id == session_id,
        )
        .order_by((PlayerTotal.earned_sp - PlayerTotal.punishments).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    user_ids = [r.user_id for r in rows]
    name_avatar_map: dict = {}
    per_user_reactions_session: dict = {}
    per_user_stanks_session: dict = {}

    if user_ids:
        name_avatar_map = await players_repo.display_names_and_avatars(session, guild_id, user_ids)

        # Session counters from player_totals
        for r in rows:
            uid = int(r.user_id)
            per_user_reactions_session[uid] = r.reactions_in_session
            per_user_stanks_session[uid] = r.stanks_in_session

    # Chain counters from player_chain_totals
    per_user_reactions_chain: dict = {}
    per_user_stanks_chain: dict = {}
    if session_id is not None:
        live_chain = await chains_repo.current_chain(session, guild_id, altar.id)
        if live_chain is not None:
            chain_totals_stmt = (
                select(PlayerChainTotal)
                .where(
                    PlayerChainTotal.guild_id == guild_id,
                    PlayerChainTotal.chain_id == live_chain.id,
                    PlayerChainTotal.user_id.in_(user_ids) if user_ids else False,
                )
            )
            chain_rows = (await session.execute(chain_totals_stmt)).scalars().all()
            for r in chain_rows:
                uid = int(r.user_id)
                per_user_reactions_chain[uid] = r.reactions_in_chain
                per_user_stanks_chain[uid] = r.stanks_in_chain

    rankings = []
    for r in rows:
        uid = int(r.user_id)
        name, avatar = name_avatar_map.get(uid, (str(uid), None))
        rankings.append({
            "user_id": str(r.user_id),
            "display_name": name,
            "discord_avatar": avatar,
            "earned_sp": r.earned_sp,
            "punishments": r.punishments,
            "net": r.earned_sp - r.punishments,
            "reactions_in_chain": per_user_reactions_chain.get(uid, 0),
            "reactions_in_session": per_user_reactions_session.get(uid, 0),
            "stanks_in_chain": per_user_stanks_chain.get(uid, 0),
            "stanks_in_session": per_user_stanks_session.get(uid, 0),
        })

    return MsgPackResponse(
        {"rankings": rankings, "has_more": len(rankings) >= limit},
        request,
    )


@router.get("/api/player/{user_id}")
async def api_player(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
):
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.services import achievements as achievements_svc
    from stankbot.services import history_service
    from stankbot.services.session_service import SessionService

    try:
        uid = int(user_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid user ID") from err

    player = await players_repo.get(session, guild_id, uid)
    if player is None:
        return MsgPackResponse({"error": "Player not found"}, request, status_code=404)

    session_svc = SessionService(session)
    current_session_id = await session_svc.current(guild_id)
    both = await history_service.user_summary_both(
        session, guild_id, uid, current_session_id
    )

    rank = await events_repo.user_rank(session, guild_id, uid, session_id=current_session_id)
    streak = await _compute_stank_streak(session, guild_id, uid)

    badge_keys = await achievements_svc.badges_for(session, guild_id, uid)
    badge_set = set(badge_keys)

    achievement_catalog = [
        {
            "key": row["key"],
            "name": row["name"],
            "description": row["description"],
            "icon": row["icon"],
            "unlocked": row["key"] in badge_set,
        }
        for row in achievements_svc.catalog_rows()
    ]

    return MsgPackResponse(
        {
            "user_id": str(uid),
            "display_name": player.display_name or str(uid),
            "discord_avatar": player.discord_avatar,
            "rank": rank,
            "stank_streak": streak,
            "session": {
                "earned_sp": both.session.earned_sp,
                "punishments": both.session.punishments,
                "net": both.session.earned_sp - both.session.punishments,
            },
            "alltime": {
                "earned_sp": both.alltime.earned_sp,
                "punishments": both.alltime.punishments,
                "chains_started": both.alltime.chains_started,
                "chains_broken": both.alltime.chains_broken,
            },
            "achievements": achievement_catalog,
            "last_stank_at": utc_isoformat(both.alltime.last_stank_at),
        },
        request,
    )


@router.get("/api/players/batch")
async def api_players_batch(
    request: Request,
    ids: str = Query(..., description="Comma-separated user IDs"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from stankbot.db.repositories import players as players_repo

    user_ids: list[int] = []
    for raw in ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            user_ids.append(int(raw))
        except ValueError:
            continue
        if len(user_ids) >= 100:
            break

    names = await players_repo.display_names(session, guild_id, user_ids)
    return MsgPackResponse(
        [{"user_id": str(uid), "display_name": names.get(uid, str(uid))} for uid in user_ids],
        request,
    )


@router.get("/api/players/{user_id}/history")
async def api_player_history(
    user_id: str,
    request: Request,
    window: str = Query("30d", description="History window, e.g. 30d, 7d"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from datetime import timedelta

    from sqlalchemy import case, func, select

    from stankbot.db.models import Event, EventType

    try:
        uid = int(user_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid user ID") from err

    try:
        days = int(window.rstrip("d"))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))

    since = datetime.now(UTC) - timedelta(days=days)
    sp_types = [
        EventType.SP_BASE,
        EventType.SP_POSITION_BONUS,
        EventType.SP_STARTER_BONUS,
        EventType.SP_FINISH_BONUS,
        EventType.SP_REACTION,
        EventType.SP_TEAM_PLAYER,
    ]
    day = func.date(Event.created_at)
    stmt = (
        select(
            day.label("day"),
            func.sum(
                case(
                    (Event.type.in_([t.value for t in sp_types]), Event.delta),
                    else_=0,
                )
            ).label("sp"),
            func.sum(
                case(
                    (Event.type == EventType.PP_BREAK.value, Event.delta),
                    else_=0,
                )
            ).label("pp"),
        )
        .where(
            Event.guild_id == guild_id,
            Event.user_id == uid,
            Event.created_at >= since,
        )
        .group_by(day)
        .order_by(day.asc())
    )
    try:
        rows = (await session.execute(stmt)).all()
    except Exception:
        log.exception("player history query failed; falling back to empty series")
        rows = []

    series = [{"day": str(r[0]), "sp": int(r[1] or 0), "pp": int(r[2] or 0)} for r in rows]
    return MsgPackResponse({"user_id": str(uid), "window_days": days, "series": series}, request)


@router.get("/api/achievements")
async def api_achievements(
    request: Request,
    user_id: str | None = Query(None, description="Optional user to mark earned badges"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from stankbot.services import achievements as achievements_svc

    unlocked: set[str] = set()
    if user_id is not None:
        try:
            uid = int(user_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail="Invalid user ID") from err
        unlocked = set(await achievements_svc.badges_for(session, guild_id, uid))

    catalog = [
        {
            "key": row["key"],
            "name": row["name"],
            "description": row["description"],
            "icon": row["icon"],
            "unlocked": row["key"] in unlocked,
        }
        for row in achievements_svc.catalog_rows()
    ]
    return MsgPackResponse({"achievements": catalog}, request)


@router.get("/api/player/{user_id}/chains")
async def api_player_chains(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from sqlalchemy import func, select

    from stankbot.db.models import Chain, ChainMessage

    try:
        uid = int(user_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid user ID") from err

    stmt = (
        select(
            Chain.id.label("chain_id"),
            Chain.started_at,
            Chain.broken_at,
            Chain.final_length,
            Chain.final_unique,
            func.count(ChainMessage.message_id).label("user_stanks"),
        )
        .join(ChainMessage, ChainMessage.chain_id == Chain.id)
        .where(
            Chain.guild_id == guild_id,
            ChainMessage.user_id == uid,
        )
        .group_by(Chain.id)
        .order_by(func.max(ChainMessage.created_at).desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).all()

    return MsgPackResponse(
        [
            {
                "chain_id": r.chain_id,
                "started_at": utc_isoformat(r.started_at),
                "broken_at": utc_isoformat(r.broken_at),
                "length": r.final_length or 0,
                "unique_contributors": r.final_unique or 0,
                "user_stanks": int(r.user_stanks or 0),
            }
            for r in rows
        ],
        request,
    )


@router.get("/api/chain/{chain_id}")
async def api_chain(
    chain_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from stankbot.db.models import Altar, Chain
    from stankbot.db.repositories import chains as chains_repo
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services import history_service, scoring_service
    from stankbot.services.session_service import SessionService
    from stankbot.services.settings_service import SettingsService

    summary = await history_service.chain_summary(session, guild_id, chain_id)
    if summary is None:
        return MsgPackResponse({"error": "Chain not found"}, request, status_code=404)

    # Fetch chain + altar for scoring config + altar name
    chain_row = await session.get(Chain, chain_id)
    assert chain_row is not None  # validated by chain_summary above
    altar = await session.get(Altar, chain_row.altar_id)
    assert altar is not None
    config = await SettingsService(session).effective_scoring(guild_id, altar)
    altar_name = altar.display_name or f"Altar #{altar.id}"

    # If the chain is still open but its originating session has since ended,
    # point the back-link at the current active session instead.
    effective_session_id = summary.session_id
    if summary.broken_at is None and summary.session_id is not None:
        current_session_id = await SessionService(session).current(guild_id)
        if current_session_id and current_session_id != summary.session_id:
            effective_session_id = current_session_id

    total_reactions = await reaction_awards_repo.count_for_chain(
        session, guild_id=guild_id, chain_id=chain_id
    )
    per_user_reactions = await reaction_awards_repo.count_per_user_for_chain(
        session, guild_id=guild_id, chain_id=chain_id
    )
    per_user_stanks = await events_repo.count_sp_base_per_user_for_chain(
        session, guild_id=guild_id, chain_id=chain_id
    )
    lb_rows = await events_repo.leaderboard_for_chain(session, guild_id, chain_id)
    user_ids = [uid for uid, _, _ in lb_rows]
    name_avatar_map = (
        await players_repo.display_names_and_avatars(session, guild_id, user_ids)
        if user_ids else {}
    )
    leaderboard = [
        {
            "user_id": str(uid),
            "display_name": name_avatar_map.get(uid, (str(uid), None))[0],
            "discord_avatar": name_avatar_map.get(uid, (str(uid), None))[1],
            "earned_sp": sp,
            "punishments": pp,
            "net": sp - pp,
            "reactions_in_chain": per_user_reactions.get(uid, 0),
            "stanks_in_chain": per_user_stanks.get(uid, 0),
        }
        for uid, sp, pp in lb_rows
    ]

    # Build timeline from chain_messages (single source of truth for positions)
    messages = await chains_repo.messages_in_chain(session, chain_id)
    timeline = []
    timeline_user_ids: set[int] = set()
    for msg in messages:
        timeline_user_ids.add(msg.user_id)
        timeline.append({
            "position": msg.position,
            "user_id": str(msg.user_id),
            "created_at": utc_isoformat(msg.created_at),
            "sp_awarded": scoring_service.stank_sp(msg.position, config),
        })

    # Resolve display names for timeline users not already in leaderboard names map
    missing_ids = [uid for uid in timeline_user_ids if uid not in name_avatar_map]
    if missing_ids:
        extra_names = await players_repo.display_names_and_avatars(session, guild_id, missing_ids)
        name_avatar_map.update(extra_names)

    for entry in timeline:
        uid = int(str(entry["user_id"]))
        name, avatar = name_avatar_map.get(uid, (str(uid), None))
        entry["display_name"] = name
        entry["discord_avatar"] = avatar

    return MsgPackResponse(
        {
            "chain_id": summary.chain_id,
            "session_id": effective_session_id,
            "altar_name": altar_name,
            "rolled_over": summary.broken_at is None and effective_session_id != summary.session_id,
            "started_at": utc_isoformat(summary.started_at),
            "broken_at": utc_isoformat(summary.broken_at),
            "length": summary.length,
            "unique_contributors": summary.unique_contributors,
            "starter_user_id": str(summary.starter_user_id) if summary.starter_user_id is not None else None,
            "broken_by_user_id": str(summary.broken_by_user_id) if summary.broken_by_user_id is not None else None,
            "contributors": [[str(uid), count] for uid, count in summary.contributors],
            "total_reactions": total_reactions,
            "timeline": timeline,
            "leaderboard": leaderboard,
            "names": {
                str(uid): name_avatar_map.get(uid, (str(uid), None))[0]
                for uid in user_ids
            },
        },
        request,
    )


@router.get("/api/sessions")
async def api_sessions(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from sqlalchemy import case, func, select

    from stankbot.db.models import Event, EventType

    # Fetch the 50 most recent sessions
    sessions_stmt = (
        select(Event.id, Event.created_at)
        .where(Event.guild_id == guild_id, Event.type == EventType.SESSION_START)
        .order_by(Event.id.desc())
        .limit(50)
    )
    session_rows = (await session.execute(sessions_stmt)).all()
    session_ids = [int(r[0]) for r in session_rows]

    # Aggregate stats per session in one query (includes ended_at, totals)
    sp_types = [
        EventType.SP_BASE,
        EventType.SP_POSITION_BONUS,
        EventType.SP_STARTER_BONUS,
        EventType.SP_FINISH_BONUS,
        EventType.SP_REACTION,
        EventType.SP_TEAM_PLAYER,
    ]
    stats_stmt = (
        select(
            Event.session_id,
            func.count(func.distinct(case((Event.type == EventType.SP_BASE, Event.user_id)))).label("unique_stankers"),
            func.count(case((Event.type == EventType.SP_BASE, 1))).label("stanks"),
            func.count(func.distinct(case((Event.type == EventType.CHAIN_START, Event.chain_id)))).label("chains"),
            func.count(case((Event.type == EventType.SP_REACTION, 1))).label("reactions"),
            func.coalesce(
                func.sum(case((Event.type.in_([t.value for t in sp_types]), Event.delta), else_=0)),
                0,
            ).label("total_sp"),
            func.coalesce(
                func.sum(case((Event.type == EventType.PP_BREAK, Event.delta), else_=0)),
                0,
            ).label("total_pp"),
            func.max(case((Event.type == EventType.SESSION_END, Event.created_at))).label("ended_at"),
        )
        .where(Event.guild_id == guild_id, Event.session_id.in_(session_ids))
        .group_by(Event.session_id)
    )
    stats_map: dict = {}
    for row in (await session.execute(stats_stmt)).all():
        stats_map[int(row[0])] = {
            "unique_stankers": int(row[1] or 0),
            "stanks": int(row[2] or 0),
            "chains": int(row[3] or 0),
            "reactions": int(row[4] or 0),
            "total_sp": int(row[5] or 0),
            "total_pp": int(row[6] or 0),
            "ended_at": utc_isoformat(row[7]),
        }

    return MsgPackResponse(
        [
            {
                "session_id": int(r[0]),
                "started_at": utc_isoformat(r[1]),
                "active": stats_map.get(int(r[0]), {}).get("ended_at") is None,
                **stats_map.get(int(r[0]), {"unique_stankers": 0, "stanks": 0, "chains": 0, "reactions": 0, "total_sp": 0, "total_pp": 0, "ended_at": None}),
            }
            for r in session_rows
        ],
        request,
    )


@router.get("/api/session/{session_id}")
async def api_session(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from sqlalchemy import case, func, select

    from stankbot.db.models import Chain, Event, EventType
    from stankbot.db.repositories import chains as chains_repo
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.services import history_service

    summary = await history_service.session_summary(session, guild_id, session_id)
    if summary is None:
        return MsgPackResponse({"error": "Session not found"}, request, status_code=404)

    # Include chains started in this session OR chains that have events in this
    # session (cross-session-boundary chains that survived a reset).

    chain_ids_in_events_stmt = (
        select(Event.chain_id)
        .where(
            Event.guild_id == guild_id,
            Event.session_id == session_id,
            Event.chain_id.is_not(None),
        )
        .distinct()
    )
    chain_ids_in_events = {r for (r,) in (await session.execute(chain_ids_in_events_stmt)).all()}

    chains_stmt = (
        select(Chain)
        .where(
            Chain.guild_id == guild_id,
            (Chain.session_id == session_id) | Chain.id.in_(chain_ids_in_events),
        )
        .order_by(Chain.id.desc())
    )
    chain_rows = list((await session.execute(chains_stmt)).scalars().all())

    # For open chains (no broken_at), live-compute length/unique rather than
    # relying on final_length which is only written at break time.
    chains_payload = []
    for c in chain_rows:
        if c.broken_at is None:
            live_len, live_unique = await chains_repo.chain_length_and_unique(session, c.id)
        else:
            live_len, live_unique = c.final_length or 0, c.final_unique or 0
        chains_payload.append({
            "chain_id": c.id,
            "started_at": utc_isoformat(c.started_at),
            "broken_at": utc_isoformat(c.broken_at),
            "length": live_len,
            "unique_contributors": live_unique,
            "starter_user_id": str(c.starter_user_id) if c.starter_user_id is not None else None,
            "broken_by_user_id": str(c.broken_by_user_id) if c.broken_by_user_id is not None else None,
        })

    # Aggregate SP/PP/stanks/reactions in a single query instead of 4 separate
    sp_types = [
        EventType.SP_BASE,
        EventType.SP_POSITION_BONUS,
        EventType.SP_STARTER_BONUS,
        EventType.SP_FINISH_BONUS,
        EventType.SP_REACTION,
        EventType.SP_TEAM_PLAYER,
    ]
    agg_stmt = (
        select(
            func.coalesce(
                func.sum(case((Event.type.in_([t.value for t in sp_types]), Event.delta), else_=0)),
                0,
            ).label("total_sp"),
            func.coalesce(
                func.sum(case((Event.type == EventType.PP_BREAK, Event.delta), else_=0)),
                0,
            ).label("total_pp"),
            func.count(case((Event.type == EventType.SP_BASE, 1))).label("total_stanks"),
            func.count(case((Event.type == EventType.SP_REACTION, 1))).label("total_reactions"),
        )
        .where(Event.guild_id == guild_id, Event.session_id == session_id)
    )
    agg_row = (await session.execute(agg_stmt)).one()
    total_sp = int(agg_row.total_sp or 0)
    total_pp = int(agg_row.total_pp or 0)
    total_stanks = int(agg_row.total_stanks or 0)
    total_reactions = int(agg_row.total_reactions or 0)

    # Session leaderboard — top 10 by net SP via player_totals cache
    lb = await events_repo.leaderboard(session, guild_id, session_id=session_id, limit=10, offset=0)
    lb_names = await players_repo.display_names_and_avatars(session, guild_id, [uid for uid, _, _ in lb]) if lb else {}
    session_leaderboard = [
        {
            "user_id": str(uid),
            "display_name": lb_names.get(uid, (str(uid), None))[0],
            "discord_avatar": lb_names.get(uid, (str(uid), None))[1],
            "earned_sp": sp,
            "punishments": pp,
            "net": sp - pp,
        }
        for uid, sp, pp in lb
    ]

    # Resolve display names for top earner/breaker
    name_ids = []
    if summary.top_earner:
        name_ids.append(int(summary.top_earner[0]))
    if summary.top_breaker:
        name_ids.append(int(summary.top_breaker[0]))
    name_map = await players_repo.display_names(session, guild_id, name_ids) if name_ids else {}

    return MsgPackResponse(
        {
            "session_id": summary.session_id,
            "started_at": utc_isoformat(summary.started_at),
            "ended_at": utc_isoformat(summary.ended_at),
            "chains_started": summary.chains_started,
            "chains_broken": summary.chains_broken,
            "total_sp": total_sp,
            "total_pp": total_pp,
            "total_stanks": total_stanks,
            "total_reactions": total_reactions,
            "session_leaderboard": session_leaderboard,
            "top_earner": [str(summary.top_earner[0]), summary.top_earner[1]] if summary.top_earner else None,
            "top_breaker": [str(summary.top_breaker[0]), summary.top_breaker[1]] if summary.top_breaker else None,
            "names": {str(uid): name for uid, name in name_map.items()},
            "chains": chains_payload,
        },
        request,
    )
