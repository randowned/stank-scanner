"""WebSocket manager and real-time broadcast helpers.

Owns the ``/ws`` WebSocket route and the singleton ``manager`` used by cogs
and the event bridge to push state updates to connected clients.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime

import msgpack
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

router = APIRouter(prefix="")


class ConnectionManager:
    """Manages WebSocket connections keyed by guild_id."""

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
    """Fetch current board state as a dict for WebSocket and HTTP clients."""
    from stankbot.db.repositories import altars as altars_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services.board_service import build_board_state
    from stankbot.services.session_service import SessionService

    altar = await altars_repo.primary(session, guild_id)
    if altar is None:
        return {}

    state = await build_board_state(
        session,
        guild_id=guild_id,
        guild_name=guild_name,
        altar=altar,
    )

    from stankbot.db.repositories import chains as chains_repo
    from stankbot.db.repositories import events as events_repo

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)
    live_chain = await chains_repo.current_chain(session, guild_id, altar.id)

    per_user_reactions_chain = (
        await reaction_awards_repo.count_per_user_for_chain(session, guild_id=guild_id, chain_id=live_chain.id)
        if live_chain is not None else {}
    )
    per_user_reactions_session = (
        await reaction_awards_repo.count_per_user_for_session(session, guild_id=guild_id, session_id=session_id)
        if session_id is not None else {}
    )
    session_reactions = (
        await reaction_awards_repo.count_for_session(session, guild_id=guild_id, session_id=session_id)
        if session_id is not None else 0
    )
    per_user_stanks_chain = (
        await events_repo.count_sp_base_per_user_for_chain(session, guild_id, live_chain.id)
        if live_chain is not None else {}
    )
    per_user_stanks_session = (
        await events_repo.count_sp_base_per_user_for_session(session, guild_id, session_id)
        if session_id is not None else {}
    )

    chain_length = state.current

    def row_to_dict(r):
        earned = r.earned_sp
        punishments = r.punishments
        uid = int(r.user_id)
        return {
            "user_id": str(r.user_id),
            "display_name": r.display_name,
            "discord_avatar": r.discord_avatar,
            "earned_sp": earned,
            "punishments": punishments,
            "net": earned - punishments,
            "reactions_in_chain": per_user_reactions_chain.get(uid, 0),
            "reactions_in_session": per_user_reactions_session.get(uid, 0),
            "stanks_in_chain": per_user_stanks_chain.get(uid, 0),
            "stanks_in_session": per_user_stanks_session.get(uid, 0),
        }

    return {
        "guild_name": state.guild_name,
        "stank_emoji": state.stank_emoji,
        "altar_sticker_url": state.altar_sticker_url,
        "session_id": session_id,
        "current": state.current,
        "current_unique": state.current_unique,
        "reactions": state.reactions,
        "session_reactions": session_reactions,
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


@router.websocket("/ws")
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
    is_dev_mock = config is not None and config.env == "dev-mock" and getattr(config, "mock_auth", False)

    session = websocket.session
    guild_id = session.get("guild") or session.get("active_guild_id")
    if guild_id is None:
        guild_id = getattr(config, "default_guild_id", None)
    if guild_id is None:
        await websocket.close(code=4003, reason="No guild selected")
        return
    guild_id = int(guild_id)

    if not is_dev_mock:
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
        from stankbot.db.engine import session_scope
        from stankbot.web.tools import guild_name_for

        async with session_scope(session_factory) as db:
            guild_name = await guild_name_for(db, guild_id)
            state = await get_board_state(db, guild_id, guild_name)
        if state:
            packed = msgpack.packb({"t": 101, "d": state}, use_single_float=True)
            await websocket.send_bytes(packed)
    except Exception as e:
        log.warning("Failed to send initial state to WS client: %s", e)

    try:
        while True:
            try:
                data = await websocket.receive_bytes()
                msg = msgpack.unpackb(data, raw=False)
                if msg.get("t") == 2:
                    await websocket.send_bytes(msgpack.packb({"t": 104}))
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.error("WebSocket error: %s", e)
                break
    finally:
        manager.disconnect(websocket, guild_id)


# ---------------------------------------------------------------------------
# Broadcast helpers — called from cogs and the mock event bridge
# ---------------------------------------------------------------------------


async def notify_chain_update(
    guild_id: int, current: int, current_unique: int, starter_user_id: int | None
) -> None:
    await manager.broadcast_json(
        guild_id,
        {
            "t": 103,
            "d": {
                "current": current,
                "current_unique": current_unique,
                "starter_user_id": str(starter_user_id) if starter_user_id is not None else None,
            },
        },
    )


async def notify_rank_update(guild_id: int, rankings: list, reactions: int | None = None, session_reactions: int | None = None) -> None:
    payload: dict = {"rankings": rankings, "updated_at": datetime.now(UTC).isoformat()}
    if reactions is not None:
        payload["reactions"] = reactions
    if session_reactions is not None:
        payload["session_reactions"] = session_reactions
    await manager.broadcast_json(guild_id, {"t": 102, "d": payload})


async def broadcast_rank_update(session_factory, guild_id: int, limit: int = 20) -> None:
    """Build the leaderboard payload and broadcast it.

    Safe to call from cogs / the event bridge — opens its own session to
    avoid entangling with the caller's transaction.
    """
    if not manager.active_connections.get(guild_id):
        return
    from stankbot.db.engine import session_scope
    from stankbot.db.repositories import events as events_repo
    from stankbot.db.repositories import players as players_repo
    from stankbot.db.repositories import reaction_awards as reaction_awards_repo
    from stankbot.services.session_service import SessionService

    async with session_scope(session_factory) as session:
        from stankbot.db.repositories import altars as altars_repo
        from stankbot.db.repositories import chains as chains_repo

        session_svc = SessionService(session)
        session_id = await session_svc.current(guild_id)
        rows = await events_repo.leaderboard(
            session, guild_id, session_id=session_id, limit=limit
        )
        user_ids = [uid for uid, _, _ in rows]
        name_avatar_map = (
            await players_repo.display_names_and_avatars(session, guild_id, user_ids)
            if user_ids
            else {}
        )
        altar = await altars_repo.primary(session, guild_id)
        live_chain = await chains_repo.current_chain(session, guild_id, altar.id) if altar else None
        per_user_reactions_chain = (
            await reaction_awards_repo.count_per_user_for_chain(session, guild_id=guild_id, chain_id=live_chain.id)
            if live_chain is not None else {}
        )
        per_user_reactions_session = (
            await reaction_awards_repo.count_per_user_for_session(session, guild_id=guild_id, session_id=session_id)
            if session_id is not None else {}
        )
        per_user_stanks_chain = (
            await events_repo.count_sp_base_per_user_for_chain(session, guild_id, live_chain.id)
            if live_chain is not None else {}
        )
        per_user_stanks_session = (
            await events_repo.count_sp_base_per_user_for_session(session, guild_id, session_id)
            if session_id is not None else {}
        )
        payload = [
            {
                "user_id": str(uid),
                "display_name": name_avatar_map.get(uid, (str(uid), None))[0],
                "discord_avatar": name_avatar_map.get(uid, (str(uid), None))[1],
                "earned_sp": sp,
                "punishments": pp,
                "net": sp - pp,
                "reactions_in_chain": per_user_reactions_chain.get(int(uid), 0),
                "reactions_in_session": per_user_reactions_session.get(int(uid), 0),
                "stanks_in_chain": per_user_stanks_chain.get(int(uid), 0),
                "stanks_in_session": per_user_stanks_session.get(int(uid), 0),
            }
            for uid, sp, pp in rows
        ]
        chain_reactions = (
            await reaction_awards_repo.count_for_chain(session, guild_id=guild_id, chain_id=live_chain.id)
            if live_chain is not None else 0
        )
        session_reactions = (
            await reaction_awards_repo.count_for_session(session, guild_id=guild_id, session_id=session_id)
            if session_id is not None else 0
        )
    await notify_rank_update(guild_id, payload, reactions=chain_reactions, session_reactions=session_reactions)


async def notify_achievement(guild_id: int, user_id: int, badge: dict) -> None:
    await manager.broadcast_json(
        guild_id,
        {"t": 105, "d": {"user_id": str(user_id), "badge": badge}},
    )


async def notify_session(
    guild_id: int, session_id: int, action: str, started_at: datetime, ended_at: datetime | None
) -> None:
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
