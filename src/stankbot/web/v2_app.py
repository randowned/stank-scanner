"""FastAPI v2 app — SvelteKit SPA + WebSocket server.

Serves:
    - /v2/* → SvelteKit static build (SPA)
    - /v2/ws → WebSocket for real-time updates
    - /v2/api/* → JSON API endpoints
    - /v2/auth → Auth check endpoint
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import msgpack
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.web.deps import (
    _is_admin_from_session,
    current_user,
    get_active_guild_id,
    get_db,
    require_guild_admin,
    require_login,
)

log = logging.getLogger(__name__)

_V2_DIR = Path(
    os.environ.get("V2_WEB_DIR", str(Path(__file__).parent.parent.parent.parent / "web"))
)
_BUILD_DIR = _V2_DIR / "build"
_API_ROUTER = APIRouter(prefix="/v2")


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, guild_id: int) -> None:
        await websocket.accept()
        self.active_connections[guild_id].append(websocket)
        log.info(
            "WebSocket connected for guild %d (total: %d)",
            guild_id,
            len(self.active_connections[guild_id]),
        )

    def disconnect(self, websocket: WebSocket, guild_id: int) -> None:
        if websocket in self.active_connections[guild_id]:
            self.active_connections[guild_id].remove(websocket)
        log.info(
            "WebSocket disconnected for guild %d (remaining: %d)",
            guild_id,
            len(self.active_connections[guild_id]),
        )

    async def broadcast(self, guild_id: int, message: bytes) -> None:
        disconnected = []
        for websocket in self.active_connections[guild_id]:
            try:
                await websocket.send_bytes(message)
            except Exception:
                disconnected.append(websocket)
        for ws in disconnected:
            self.disconnect(ws, guild_id)

    async def broadcast_json(self, guild_id: int, message: dict) -> None:
        packed = msgpack.packb(message, use_single_float=True)
        await self.broadcast(guild_id, packed)


manager = ConnectionManager()


async def get_board_state(session: AsyncSession, guild_id: int, guild_name: str) -> dict:
    """Fetch current board state as dict for WebSocket clients."""
    from stankbot.db.repositories import altars as altars_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services.board_service import build_board_state

    altar = await altars_repo.primary(session, guild_id)
    if altar is None:
        return {}

    state = await build_board_state(
        session,
        guild_id=guild_id,
        guild_name=guild_name,
        altar=altar,
    )

    from stankbot.services.session_service import SessionService

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)
    per_user_reactions = await reaction_awards_repo.count_per_user_for_session(
        session, guild_id=guild_id, session_id=session_id
    )

    chain_length = state.current

    def row_to_dict(r):
        earned = r.earned_sp
        punishments = r.punishments
        reacts = per_user_reactions.get(int(r.user_id), 0)
        return {
            "user_id": r.user_id,
            "display_name": r.display_name,
            "earned_sp": earned,
            "punishments": punishments,
            "net": earned - punishments,
            "reactions_in_session": reacts,
        }

    return {
        "guild_name": state.guild_name,
        "stank_emoji": state.stank_emoji,
        "altar_sticker_url": state.altar_sticker_url,
        "current": state.current,
        "current_unique": state.current_unique,
        "reactions": state.reactions,
        "chain_length": chain_length,
        "record": state.record,
        "record_unique": state.record_unique,
        "alltime_record": state.alltime_record,
        "alltime_record_unique": state.alltime_record_unique,
        "next_reset_at": state.next_reset_at.isoformat() if state.next_reset_at else None,
        "rankings": [row_to_dict(r) for r in state.rankings],
        "chain_starter": row_to_dict(state.chain_starter) if state.chain_starter else None,
        "chainbreaker": row_to_dict(state.chainbreaker) if state.chainbreaker else None,
    }


@_API_ROUTER.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time updates.

    Auth is read entirely from the signed session cookie — neither the
    user ID nor the guild ID is accepted from query parameters, so
    neither can be tampered with.
    """

    app_state = websocket.app.state
    session_factory = getattr(app_state, "session_factory", None)
    if session_factory is None:
        await websocket.close(code=4001, reason="No session factory")
        return

    config = getattr(app_state, "config", None)
    is_dev_mock = config is not None and config.env == "dev" and getattr(config, "mock_auth", False)

    session = websocket.session
    guild_id = session.get("guild") or session.get("active_guild_id")
    if guild_id is None:
        guild_id = getattr(config, "default_guild_id", None)
    if guild_id is None:
        await websocket.close(code=4003, reason="No guild selected")
        return
    guild_id = int(guild_id)

    if not is_dev_mock:
        # Session-based auth avoids relying on discord.py's member cache,
        # which is often incomplete in production and causes spurious 403s.
        user = session.get("user")
        if user is None:
            await websocket.close(code=4003, reason="Not authenticated")
            return
        guilds = session.get("guilds", [])
        is_member = any(int(g.get("id", 0)) == guild_id for g in guilds)
        if not is_member:
            owner_id = int(getattr(config, "owner_id", 0) or 0)
            if int(user.get("id", 0)) != owner_id:
                await websocket.close(code=4003, reason="Not in guild")
                return

    await manager.connect(websocket, guild_id)

    try:
        while True:
            try:
                data = await websocket.receive_bytes()
                msg = msgpack.unpackb(data, raw=False)

                msg_type = msg.get("t")
                if msg_type == 2:
                    await websocket.send_bytes(msgpack.packb({"t": 104}))
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.error("WebSocket error: %s", e)
                break
    finally:
        manager.disconnect(websocket, guild_id)


@_API_ROUTER.get("/ping")
async def ping() -> JSONResponse:
    """Health check for v2 API."""
    return JSONResponse({"status": "ok", "version": "v2"})


@_API_ROUTER.get("/api/env")
async def api_env(request: Request) -> JSONResponse:
    """Return runtime environment info for the SvelteKit dashboard."""
    config = request.app.state.config
    user = current_user(request)
    guild_id = get_active_guild_id(request) if user else None

    return JSONResponse(
        {
            "env": config.env,
            "guild_id": str(guild_id) if guild_id else None,
            "is_admin": _is_admin_from_session(request) if user else False,
            "mock_auth": config.mock_auth if config.env == "dev" else False,
        }
    )


@_API_ROUTER.post("/api/admin/guild")
async def api_switch_guild(
    request: Request,
    guild_id: int = Query(...),
    user: dict = Depends(require_guild_admin),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Switch the active guild for the current session (v2 API)."""
    from stankbot.services.permission_service import PermissionService

    config = request.app.state.config
    target_gid = guild_id

    if int(user["id"]) != int(getattr(config, "owner_id", 0) or 0):
        svc = PermissionService(session, owner_id=config.owner_id)
        is_admin = await svc.is_admin(
            target_gid,
            int(user["id"]),
            [],
            has_manage_guild=False,
        )
        if not is_admin:
            raise HTTPException(status_code=403, detail="not allowed to switch to this guild")

    request.session["guild"] = target_gid
    return JSONResponse({"success": True, "guild_id": target_gid})


@_API_ROUTER.get("/auth")
async def auth_check(request: Request, user: dict = Depends(require_login)) -> JSONResponse:
    """Return current user info for SvelteKit authentication."""
    return JSONResponse(
        {
            "id": str(user["id"]),
            "username": user.get("username", ""),
            "avatar": user.get("avatar"),
        }
    )


@_API_ROUTER.get("/api/guilds")
async def api_guilds(
    request: Request,
    user: dict = Depends(require_login),
) -> JSONResponse:
    """Return the user's accessible guilds merged with bot-presence info.

    Powers the header user menu's guild switcher and the admin "install to
    another guild" CTA. The bot's guild list is the owner's super-admin
    surface; regular users see only guilds they're actually in.
    """
    from stankbot.web.deps import _is_owner

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

    # Keep the active guild first, bot-present next, others last — stable
    # ordering so the dropdown doesn't shuffle when the session refreshes.
    results.sort(key=lambda g: (not g["is_active"], not g["bot_present"], g["name"].lower()))

    _ = config  # reserved for future member_count enrichment via bot cache
    return JSONResponse(results)


from stankbot.web._transport import MsgPackResponse, _accepts_msgpack  # noqa: E402,F401


@_API_ROUTER.get("/api/board")
async def api_board(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> MsgPackResponse:
    """Return current board state as msgpack or JSON."""
    from stankbot.web.deps import guild_name_for

    guild_name = await guild_name_for(session, guild_id)
    state = await get_board_state(session, guild_id, guild_name)
    return MsgPackResponse(state, request)


@_API_ROUTER.get("/api/leaderboard")
async def api_leaderboard(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> MsgPackResponse:
    """Return paginated leaderboard rows as msgpack or JSON."""
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services.session_service import SessionService

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)
    rows = await events_repo.leaderboard(
        session, guild_id, session_id=session_id, limit=limit, offset=offset
    )

    user_ids = [uid for uid, _, _ in rows]
    names = {}
    if user_ids:
        from stankbot.db.repositories import players as players_repo

        names = await players_repo.display_names(session, guild_id, user_ids)

    per_user_reactions = await reaction_awards_repo.count_per_user_for_session(
        session, guild_id=guild_id, session_id=session_id
    )

    def _row(uid: int, sp: int, pp: int) -> dict:
        reacts = per_user_reactions.get(int(uid), 0)
        return {
            "user_id": uid,
            "display_name": names.get(uid, str(uid)),
            "earned_sp": sp,
            "punishments": pp,
            "net": sp - pp,
            "reactions_in_session": reacts,
        }

    result = [_row(uid, sp, pp) for uid, sp, pp in rows]
    return MsgPackResponse(result, request)


@_API_ROUTER.get("/api/player/{user_id}")
async def api_player(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
):
    """Return player profile as msgpack or JSON."""
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
            "user_id": uid,
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


@_API_ROUTER.get("/api/players/batch")
async def api_players_batch(
    request: Request,
    ids: str = Query(..., description="Comma-separated user IDs"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    """Resolve a batch of user IDs to display names for chain/session detail pages."""
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
    result = [
        {"user_id": str(uid), "display_name": names.get(uid, str(uid))}
        for uid in user_ids
    ]
    return JSONResponse(result)


@_API_ROUTER.get("/api/players/{user_id}/history")
async def api_player_history(
    user_id: str,
    request: Request,
    window: str = Query("30d", description="History window, e.g. 30d, 7d"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    """Return per-day SP and PP for a player over the requested window."""
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

    series = [
        {"day": str(r[0]), "sp": int(r[1] or 0), "pp": int(r[2] or 0)}
        for r in rows
    ]
    return JSONResponse({"user_id": str(uid), "window_days": days, "series": series})


@_API_ROUTER.get("/api/achievements")
async def api_achievements(
    request: Request,
    user_id: str | None = Query(None, description="Optional user to mark earned badges"),
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    """Return the achievement catalog plus (optionally) which are unlocked for a user."""
    from stankbot.services import achievements as achievements_svc

    unlocked: set[str] = set()
    if user_id is not None:
        try:
            uid = int(user_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail="Invalid user ID") from err
        unlocked = set(await achievements_svc.badges_for(session, guild_id, uid))

    catalog = []
    for row in achievements_svc.catalog_rows():
        catalog.append(
            {
                "key": row["key"],
                "name": row["name"],
                "description": row["description"],
                "icon": row["icon"],
                "unlocked": row["key"] in unlocked,
            }
        )
    return JSONResponse({"achievements": catalog})


@_API_ROUTER.get("/api/chains")
async def api_chains(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
):
    """Return chain history as msgpack or JSON."""
    from sqlalchemy import select

    from stankbot.db.models import Chain

    stmt = select(Chain).where(Chain.guild_id == guild_id).order_by(Chain.id.desc()).limit(50)
    chains = list((await session.execute(stmt)).scalars().all())

    result = []
    for c in chains:
        result.append(
            {
                "chain_id": c.id,
                "started_at": c.started_at.isoformat(),
                "broken_at": c.broken_at.isoformat() if c.broken_at else None,
                "length": c.final_length or 0,
                "unique_contributors": c.final_unique or 0,
                "starter_user_id": c.starter_user_id,
                "broken_by_user_id": c.broken_by_user_id,
                "contributors": [],
            }
        )

    return MsgPackResponse(result, request)


@_API_ROUTER.get("/api/chain/{chain_id}")
async def api_chain(
    chain_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    """Return chain detail as JSON."""
    from stankbot.services import history_service

    summary = await history_service.chain_summary(session, guild_id, chain_id)
    if summary is None:
        return JSONResponse({"error": "Chain not found"}, status_code=404)

    return JSONResponse(
        {
            "chain_id": summary.chain_id,
            "started_at": summary.started_at.isoformat(),
            "broken_at": summary.broken_at.isoformat() if summary.broken_at else None,
            "length": summary.length,
            "unique_contributors": summary.unique_contributors,
            "starter_user_id": summary.starter_user_id,
            "broken_by_user_id": summary.broken_by_user_id,
            "contributors": summary.contributors,
        }
    )


@_API_ROUTER.get("/api/sessions")
async def api_sessions(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    """Return session history as JSON."""
    from sqlalchemy import select

    from stankbot.db.models import Event, EventType

    stmt = (
        select(Event.id, Event.created_at)
        .where(Event.guild_id == guild_id, Event.type == EventType.SESSION_START)
        .order_by(Event.id.desc())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()

    result = [
        {"session_id": int(r[0]), "started_at": r[1].isoformat() if r[1] else None} for r in rows
    ]
    return MsgPackResponse(result, request)


@_API_ROUTER.get("/api/session/{session_id}")
async def api_session(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
) -> JSONResponse:
    """Return session detail as JSON."""
    from sqlalchemy import select

    from stankbot.db.models import Chain
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
            "starter_user_id": c.starter_user_id,
            "broken_by_user_id": c.broken_by_user_id,
        }
        for c in chain_rows
    ]

    return JSONResponse(
        {
            "session_id": summary.session_id,
            "started_at": summary.started_at.isoformat() if summary.started_at else None,
            "ended_at": summary.ended_at.isoformat() if summary.ended_at else None,
            "chains_started": summary.chains_started,
            "chains_broken": summary.chains_broken,
            "top_earner": summary.top_earner,
            "top_breaker": summary.top_breaker,
            "chains": chains_payload,
        }
    )


async def notify_chain_update(
    guild_id: int, current: int, current_unique: int, starter_user_id: int | None
) -> None:
    """Broadcast chain update to all connected clients."""
    await manager.broadcast_json(
        guild_id,
        {
            "t": 103,
            "d": {
                "current": current,
                "current_unique": current_unique,
                "starter_user_id": starter_user_id,
            },
        },
    )


async def notify_rank_update(guild_id: int, rankings: list) -> None:
    """Broadcast rank update to all connected clients."""
    await manager.broadcast_json(
        guild_id,
        {
            "t": 102,
            "d": {"rankings": rankings, "updated_at": datetime.now(UTC).isoformat()},
        },
    )


async def broadcast_rank_update(session_factory, guild_id: int, limit: int = 20) -> None:
    """Convenience: build the leaderboard payload and broadcast it.

    Safe to call from cogs / the event bridge — it opens its own session
    to avoid entangling with the caller's transaction.
    """
    if not manager.active_connections.get(guild_id):
        return
    from stankbot.db.engine import session_scope
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services.session_service import SessionService

    async with session_scope(session_factory) as session:
        session_svc = SessionService(session)
        session_id = await session_svc.current(guild_id)
        rows = await events_repo.leaderboard(
            session, guild_id, session_id=session_id, limit=limit
        )
        user_ids = [uid for uid, _, _ in rows]
        names = (
            await players_repo.display_names(session, guild_id, user_ids)
            if user_ids
            else {}
        )
        per_user_reactions = await reaction_awards_repo.count_per_user_for_session(
            session, guild_id=guild_id, session_id=session_id
        )
        payload = [
            {
                "user_id": uid,
                "display_name": names.get(uid, str(uid)),
                "earned_sp": sp,
                "punishments": pp,
                "net": sp - pp,
                "reactions_in_session": per_user_reactions.get(int(uid), 0),
            }
            for uid, sp, pp in rows
        ]
    await notify_rank_update(guild_id, payload)


async def notify_achievement(guild_id: int, user_id: int, badge: dict) -> None:
    """Broadcast achievement unlock."""
    await manager.broadcast_json(
        guild_id,
        {"t": 105, "d": {"user_id": user_id, "badge": badge}},
    )


async def notify_session(
    guild_id: int, session_id: int, action: str, started_at: datetime, ended_at: datetime | None
) -> None:
    """Broadcast session change."""
    await manager.broadcast_json(
        guild_id,
        {
            "t": 106,
            "d": {
                "session_id": session_id,
                "action": action,
                "started_at": started_at.isoformat() if started_at else None,
                "ended_at": ended_at.isoformat() if ended_at else None,
            },
        },
    )
