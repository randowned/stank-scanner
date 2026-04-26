"""Public JSON API routes for the SvelteKit dashboard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

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

    # Paginated rankings only — fetch next page from player_totals.
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.services.session_service import SessionService

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)
    rows = await events_repo.leaderboard(
        session, guild_id, session_id=session_id, limit=limit, offset=offset
    )

    user_ids = [uid for uid, _, _ in rows]
    name_avatar_map: dict = {}
    if user_ids:
        name_avatar_map = await players_repo.display_names_and_avatars(session, guild_id, user_ids)

    rankings = []
    for uid, sp, pp in rows:
        name, avatar = name_avatar_map.get(uid, (str(uid), None))
        rankings.append({
            "user_id": str(uid),
            "display_name": name,
            "discord_avatar": avatar,
            "earned_sp": sp,
            "punishments": pp,
            "net": sp - pp,
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
    from stankbot.db.repositories import players as players_repo
    from stankbot.services import achievements as achievements_svc
    from stankbot.services import history_service

    try:
        uid = int(user_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid user ID") from err

    player = await players_repo.get(session, guild_id, uid)
    if player is None:
        return MsgPackResponse({"error": "Player not found"}, request, status_code=404)

    summary = await history_service.user_summary(session, guild_id, uid)
    badge_keys = await achievements_svc.badges_for(session, guild_id, uid)
    badge_set = set(badge_keys)
    badges = []
    for key in badge_keys:
        defn = achievements_svc.definition(key)
        if defn:
            badges.append(
                {
                    "key": defn.key,
                    "name": defn.name,
                    "icon": defn.icon,
                    "description": defn.description,
                    "unlocked_at": datetime.now(UTC).isoformat(),
                }
            )

    # Full achievement catalog with unlock status
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
            "session": {
                "earned_sp": summary.earned_sp,
                "punishments": summary.punishments,
                "net": summary.earned_sp - summary.punishments,
            },
            "alltime": {
                "earned_sp": summary.earned_sp,
                "punishments": summary.punishments,
                "chains_started": summary.chains_started,
                "chains_broken": summary.chains_broken,
            },
            "badges": badges,
            "achievements": achievement_catalog,
            "last_stank_at": summary.last_stank_at.isoformat() if summary.last_stank_at else None,
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



@router.get("/api/chain/{chain_id}")
async def api_chain(
    chain_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict = Depends(require_guild_member),
) -> MsgPackResponse:
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services import history_service
    from stankbot.services.session_service import SessionService

    summary = await history_service.chain_summary(session, guild_id, chain_id)
    if summary is None:
        return MsgPackResponse({"error": "Chain not found"}, request, status_code=404)

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
            "reactions_in_session": per_user_reactions.get(uid, 0),
        }
        for uid, sp, pp in lb_rows
    ]

    return MsgPackResponse(
        {
            "chain_id": summary.chain_id,
            "session_id": effective_session_id,
            "rolled_over": summary.broken_at is None and effective_session_id != summary.session_id,
            "started_at": summary.started_at.isoformat(),
            "broken_at": summary.broken_at.isoformat() if summary.broken_at else None,
            "length": summary.length,
            "unique_contributors": summary.unique_contributors,
            "starter_user_id": str(summary.starter_user_id) if summary.starter_user_id is not None else None,
            "broken_by_user_id": str(summary.broken_by_user_id) if summary.broken_by_user_id is not None else None,
            "contributors": [[str(uid), count] for uid, count in summary.contributors],
            "total_reactions": total_reactions,
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

    # Determine which session is still active (no SESSION_END event)
    ended_stmt = (
        select(Event.session_id)
        .where(Event.guild_id == guild_id, Event.type == EventType.SESSION_END, Event.session_id.in_(session_ids))
    )
    ended_ids = {int(r[0]) for r in (await session.execute(ended_stmt)).all()}

    # Aggregate stats per session in one query
    stats_stmt = (
        select(
            Event.session_id,
            func.count(func.distinct(case((Event.type == EventType.SP_BASE, Event.user_id)))).label("unique_stankers"),
            func.count(case((Event.type == EventType.SP_BASE, 1))).label("stanks"),
            func.count(func.distinct(case((Event.type == EventType.CHAIN_START, Event.chain_id)))).label("chains"),
            func.count(case((Event.type == EventType.SP_REACTION, 1))).label("reactions"),
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
        }

    return MsgPackResponse(
        [
            {
                "session_id": int(r[0]),
                "started_at": r[1].isoformat() if r[1] else None,
                "active": int(r[0]) not in ended_ids,
                **stats_map.get(int(r[0]), {"unique_stankers": 0, "stanks": 0, "chains": 0, "reactions": 0}),
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
    from sqlalchemy import func, select

    from stankbot.db.models import Chain, Event, EventType
    from stankbot.db.repositories import players as players_repo
    from stankbot.services import history_service

    summary = await history_service.session_summary(session, guild_id, session_id)
    if summary is None:
        return MsgPackResponse({"error": "Session not found"}, request, status_code=404)

    # Include chains started in this session OR chains that have events in this
    # session (cross-session-boundary chains that survived a reset).
    from stankbot.db.repositories import chains as chains_repo

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
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "broken_at": c.broken_at.isoformat() if c.broken_at else None,
            "length": live_len,
            "unique_contributors": live_unique,
            "starter_user_id": str(c.starter_user_id) if c.starter_user_id is not None else None,
            "broken_by_user_id": str(c.broken_by_user_id) if c.broken_by_user_id is not None else None,
        })

    # Count total stanks (SP_BASE events) and reactions in session
    total_stanks_stmt = select(func.count(Event.id)).where(
        Event.guild_id == guild_id,
        Event.session_id == session_id,
        Event.type == EventType.SP_BASE,
    )
    total_stanks = int((await session.execute(total_stanks_stmt)).scalar_one() or 0)
    total_reactions_stmt = select(func.count(Event.id)).where(
        Event.guild_id == guild_id,
        Event.session_id == session_id,
        Event.type == EventType.SP_REACTION,
    )
    total_reactions = int((await session.execute(total_reactions_stmt)).scalar_one() or 0)

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
            "started_at": summary.started_at.isoformat() if summary.started_at else None,
            "ended_at": summary.ended_at.isoformat() if summary.ended_at else None,
            "chains_started": summary.chains_started,
            "chains_broken": summary.chains_broken,
            "top_earner": [str(summary.top_earner[0]), summary.top_earner[1]] if summary.top_earner else None,
            "top_breaker": [str(summary.top_breaker[0]), summary.top_breaker[1]] if summary.top_breaker else None,
            "total_stanks": total_stanks,
            "total_reactions": total_reactions,
            "names": {str(uid): name for uid, name in name_map.items()},
            "chains": chains_payload,
        },
        request,
    )
