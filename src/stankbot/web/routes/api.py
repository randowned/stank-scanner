"""Public JSON API routes for the SvelteKit dashboard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.web.tools import (
    _is_admin_from_session,
    current_user,
    get_active_guild_id,
    get_db,
    require_login,
)
from stankbot.web.transport import MsgPackResponse
from stankbot.web.ws import get_board_state

router = APIRouter(prefix="")
log = logging.getLogger(__name__)


@router.get("/ping")
async def ping() -> JSONResponse:
    return JSONResponse({"status": "ok"})


_BOT_INVITE_SCOPES = "bot+applications.commands"
_BOT_INVITE_PERMISSIONS = 2147560448  # Send Messages + Add Reactions + Read Message History + Use External Emojis + Use External Stickers


@router.get("/api/env")
async def api_env(request: Request) -> JSONResponse:
    config = request.app.state.config
    user = current_user(request)
    guild_id = get_active_guild_id(request) if user else None
    invite_url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={config.discord_app_id}"
        f"&permissions={_BOT_INVITE_PERMISSIONS}"
        f"&scope={_BOT_INVITE_SCOPES}"
    )
    return JSONResponse(
        {
            "env": config.env,
            "guild_id": str(guild_id) if guild_id else None,
            "is_admin": _is_admin_from_session(request) if user else False,
            "mock_auth": config.mock_auth if config.env == "dev-mock" else False,
            "invite_url": invite_url,
        }
    )


@router.get("/api/guilds")
async def api_guilds(
    request: Request,
    user: dict = Depends(require_login),
) -> JSONResponse:
    """Return the user's accessible guilds merged with bot-presence info."""
    from stankbot.web.tools import _is_owner

    config = request.app.state.config
    bot_guilds: list[dict] = getattr(request.app.state, "bot_guilds", [])
    bot_guild_ids = {int(g["id"]) for g in bot_guilds}
    bot_guild_by_id = {int(g["id"]): g for g in bot_guilds}

    user_guilds = request.session.get("guilds", [])
    is_owner = _is_owner(request)
    active_guild_id = request.session.get("guild") or request.session.get("active_guild_id")

    def icon_url(guild_id: int, icon_hash: str | None) -> str | None:
        if not icon_hash:
            return None
        ext = "gif" if icon_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{ext}"

    results: list[dict] = []
    seen: set[int] = set()

    for g in user_guilds:
        gid = int(g.get("id", 0))
        if gid == 0 or gid in seen:
            continue
        seen.add(gid)
        perms = int(g.get("permissions", 0))
        is_admin = is_owner or bool(perms & 0x20)
        results.append(
            {
                "id": str(gid),
                "name": g.get("name", ""),
                "icon_url": icon_url(gid, g.get("icon")),
                "bot_present": gid in bot_guild_ids,
                "is_admin": is_admin,
                "is_owner": is_owner,
                "is_active": active_guild_id is not None and int(active_guild_id) == gid,
            }
        )

    if is_owner:
        for gid, g in bot_guild_by_id.items():
            if gid in seen:
                continue
            results.append(
                {
                    "id": str(gid),
                    "name": str(g.get("name", "")),
                    "icon_url": icon_url(gid, g.get("icon")),
                    "bot_present": True,
                    "is_admin": True,
                    "is_owner": True,
                    "is_active": active_guild_id is not None and int(active_guild_id) == gid,
                }
            )

    results.sort(key=lambda g: (not g["is_active"], not g["bot_present"], g["name"].lower()))
    _ = config  # reserved for future member_count enrichment via bot cache
    return JSONResponse(results)


@router.get("/api/board")
async def api_board(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> MsgPackResponse:
    from stankbot.web.tools import guild_name_for

    guild_name = await guild_name_for(session, guild_id)
    state = await get_board_state(session, guild_id, guild_name)
    return MsgPackResponse(state, request)


@router.get("/api/leaderboard")
async def api_leaderboard(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> MsgPackResponse:
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services.session_service import SessionService

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)
    rows = await events_repo.leaderboard(
        session, guild_id, session_id=session_id, limit=limit, offset=offset
    )

    user_ids = [uid for uid, _, _ in rows]
    name_avatar_map: dict = {}
    if user_ids:
        from stankbot.db.repositories import players as players_repo

        name_avatar_map = await players_repo.display_names_and_avatars(session, guild_id, user_ids)

    from stankbot.db.repositories import altars as altars_repo
    from stankbot.db.repositories import chains as chains_repo

    altar = await altars_repo.primary(session, guild_id)
    live_chain = await chains_repo.current_chain(session, guild_id, altar.id) if altar else None
    if live_chain is not None:
        per_user_reactions = await reaction_awards_repo.count_per_user_for_chain(
            session, guild_id=guild_id, chain_id=live_chain.id
        )
    else:
        per_user_reactions = await reaction_awards_repo.count_per_user_for_session(
            session, guild_id=guild_id, session_id=session_id
        )

    per_user_stanks = await events_repo.count_sp_base_per_user_for_session(
        session, guild_id, session_id
    ) if session_id is not None else {}

    def _row(uid: int, sp: int, pp: int) -> dict:
        reacts = per_user_reactions.get(int(uid), 0)
        stanks = per_user_stanks.get(int(uid), 0)
        name, avatar = name_avatar_map.get(uid, (str(uid), None))
        return {
            "user_id": str(uid),
            "display_name": name,
            "discord_avatar": avatar,
            "earned_sp": sp,
            "punishments": pp,
            "net": sp - pp,
            "reactions_in_session": reacts,
            "stanks_in_session": stanks,
        }

    return MsgPackResponse([_row(uid, sp, pp) for uid, sp, pp in rows], request)


@router.get("/api/player/{user_id}")
async def api_player(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
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
        return JSONResponse({"error": "Player not found"}, status_code=404)

    summary = await history_service.user_summary(session, guild_id, uid)
    badge_keys = await achievements_svc.badges_for(session, guild_id, uid)
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
) -> JSONResponse:
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
    return JSONResponse(
        [{"user_id": str(uid), "display_name": names.get(uid, str(uid))} for uid in user_ids]
    )


@router.get("/api/players/{user_id}/history")
async def api_player_history(
    user_id: str,
    request: Request,
    window: str = Query("30d", description="History window, e.g. 30d, 7d"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
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
    return JSONResponse({"user_id": str(uid), "window_days": days, "series": series})


@router.get("/api/achievements")
async def api_achievements(
    request: Request,
    user_id: str | None = Query(None, description="Optional user to mark earned badges"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
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
    return JSONResponse({"achievements": catalog})



@router.get("/api/chain/{chain_id}")
async def api_chain(
    chain_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services import history_service

    summary = await history_service.chain_summary(session, guild_id, chain_id)
    if summary is None:
        return JSONResponse({"error": "Chain not found"}, status_code=404)

    total_reactions = await reaction_awards_repo.count_for_chain(
        session, guild_id=guild_id, chain_id=chain_id
    )

    return JSONResponse(
        {
            "chain_id": summary.chain_id,
            "started_at": summary.started_at.isoformat(),
            "broken_at": summary.broken_at.isoformat() if summary.broken_at else None,
            "length": summary.length,
            "unique_contributors": summary.unique_contributors,
            "starter_user_id": str(summary.starter_user_id) if summary.starter_user_id is not None else None,
            "broken_by_user_id": str(summary.broken_by_user_id) if summary.broken_by_user_id is not None else None,
            "contributors": [[str(uid), count] for uid, count in summary.contributors],
            "total_reactions": total_reactions,
        }
    )


@router.get("/api/sessions")
async def api_sessions(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    from sqlalchemy import select

    from stankbot.db.models import Event, EventType

    stmt = (
        select(Event.id, Event.created_at)
        .where(Event.guild_id == guild_id, Event.type == EventType.SESSION_START)
        .order_by(Event.id.desc())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()
    return MsgPackResponse(
        [
            {"session_id": int(r[0]), "started_at": r[1].isoformat() if r[1] else None}
            for r in rows
        ],
        request,
    )


@router.get("/api/session/{session_id}")
async def api_session(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    from sqlalchemy import func, select

    from stankbot.db.models import Chain, Event, EventType
    from stankbot.db.repositories import players as players_repo
    from stankbot.services import history_service

    summary = await history_service.session_summary(session, guild_id, session_id)
    if summary is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    chains_stmt = (
        select(Chain)
        .where(Chain.guild_id == guild_id, Chain.session_id == session_id)
        .order_by(Chain.id.desc())
    )
    chain_rows = list((await session.execute(chains_stmt)).scalars().all())
    chains_payload = [
        {
            "chain_id": c.id,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "broken_at": c.broken_at.isoformat() if c.broken_at else None,
            "length": c.final_length or 0,
            "unique_contributors": c.final_unique or 0,
            "starter_user_id": str(c.starter_user_id) if c.starter_user_id is not None else None,
            "broken_by_user_id": str(c.broken_by_user_id) if c.broken_by_user_id is not None else None,
        }
        for c in chain_rows
    ]

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

    return JSONResponse(
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
        }
    )
