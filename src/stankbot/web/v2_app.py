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

from stankbot.web.deps import get_active_guild_id, get_db, require_login

log = logging.getLogger(__name__)

_V2_DIR = Path(os.environ.get("V2_WEB_DIR", str(Path(__file__).parent.parent.parent.parent / "web")))
_BUILD_DIR = _V2_DIR / "build"
_API_ROUTER = APIRouter(prefix="/v2")


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, guild_id: int) -> None:
        await websocket.accept()
        self.active_connections[guild_id].append(websocket)
        log.info("WebSocket connected for guild %d (total: %d)", guild_id, len(self.active_connections[guild_id]))

    def disconnect(self, websocket: WebSocket, guild_id: int) -> None:
        if websocket in self.active_connections[guild_id]:
            self.active_connections[guild_id].remove(websocket)
        log.info("WebSocket disconnected for guild %d (remaining: %d)", guild_id, len(self.active_connections[guild_id]))

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

    def row_to_dict(r):
        return {"user_id": r.user_id, "display_name": r.display_name, "earned_sp": r.earned_sp, "punishments": r.punishments}

    return {
        "guild_name": state.guild_name,
        "stank_emoji": state.stank_emoji,
        "altar_sticker_url": state.altar_sticker_url,
        "current": state.current,
        "current_unique": state.current_unique,
        "record": state.record,
        "record_unique": state.record_unique,
        "alltime_record": state.alltime_record,
        "alltime_record_unique": state.alltime_record_unique,
        "next_reset_at": state.next_reset_at.isoformat() if state.next_reset_at else None,
        "rankings": [row_to_dict(r) for r in state.rankings],
        "chain_starter": row_to_dict(state.chain_starter) if state.chain_starter else None,
        "chainbreaker": row_to_dict(state.chainbreaker) if state.chainbreaker else None,
    }


@_API_ROUTER.websocket("ws")
async def websocket_endpoint(
    websocket: WebSocket,
    request: Request,
    guild_id: int = Query(...),
    user_id: int = Query(...),
) -> None:
    """WebSocket endpoint for real-time updates."""

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        await websocket.close(code=4001, reason="No session factory")
        return

    session = None
    try:
        async with session_factory() as session:
            if not _is_guild_member_check(request, guild_id, user_id):
                await websocket.close(code=4003, reason="Not in guild")
                return

            await manager.connect(websocket, guild_id)

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
        if session is not None:
            await session.aclose()
        manager.disconnect(websocket, guild_id)


def _is_guild_member_check(request: Request, guild_id: int, user_id: int) -> bool:
    """Check if user is a member of the guild using the bot."""

    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        return False
    guild = bot.get_guild(guild_id)
    if guild is None:
        return False
    member = guild.get_member(user_id)
    return member is not None


@_API_ROUTER.get("auth")
async def auth_check(request: Request, user: dict = Depends(require_login)) -> JSONResponse:
    """Return current user info for SvelteKit authentication."""
    return JSONResponse(
        {
            "id": str(user["id"]),
            "username": user.get("username", ""),
            "avatar": user.get("avatar"),
        }
    )


def _accepts_msgpack(request: Request) -> bool:
    """Check if client prefers msgpack over JSON."""
    accept = request.headers.get("accept", "")
    return "msgpack" in accept.lower()


class MsgPackResponse(JSONResponse):
    """Response that switches between msgpack and JSON based on Accept header."""

    def __init__(self, content: dict, request: Request) -> None:
        if _accepts_msgpack(request):
            self._msgpack_body = msgpack.packb(content, use_single_float=True)
            super().__init__(content, media_type="application/msgpack")
        else:
            super().__init__(content)


@_API_ROUTER.get("api/board")
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


@_API_ROUTER.get("api/player/{user_id}")
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
        }
    )


@_API_ROUTER.get("api/chains")
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


@_API_ROUTER.get("api/chain/{chain_id}")
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


@_API_ROUTER.get("api/sessions")
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

    result = [{"session_id": int(r[0]), "started_at": r[1].isoformat() if r[1] else None} for r in rows]
    return MsgPackResponse(result, request)


@_API_ROUTER.get("api/session/{session_id}")
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
    await session.execute(chains_stmt)

    return JSONResponse(
        {
            "session_id": summary.session_id,
            "started_at": summary.started_at.isoformat() if summary.started_at else None,
            "ended_at": summary.ended_at.isoformat() if summary.ended_at else None,
            "chains_started": summary.chains_started,
            "chains_broken": summary.chains_broken,
            "top_earner": summary.top_earner,
            "top_breaker": summary.top_breaker,
        }
    )


async def notify_chain_update(guild_id: int, current: int, current_unique: int, starter_user_id: int | None) -> None:
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
        }
    )


async def notify_rank_update(guild_id: int, rankings: list) -> None:
    """Broadcast rank update to all connected clients."""
    await manager.broadcast_json(
        guild_id,
        {
            "t": 102,
            "d": {"rankings": rankings, "updated_at": datetime.now(UTC).isoformat()},
        }
    )


async def notify_achievement(guild_id: int, user_id: int, badge: dict) -> None:
    """Broadcast achievement unlock."""
    await manager.broadcast_json(
        guild_id,
        {"t": 105, "d": {"user_id": user_id, "badge": badge}},
    )


async def notify_session(guild_id: int, session_id: int, action: str, started_at: datetime, ended_at: datetime | None) -> None:
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
        }
    )
