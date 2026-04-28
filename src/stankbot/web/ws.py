"""WebSocket manager and real-time broadcast helpers.

Owns the ``/ws`` WebSocket route and the singleton ``manager`` used by cogs
and the event bridge to push state updates to connected clients.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import msgpack
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# WS message type constants (shared with frontend ws.ts)
MSG_TYPE_PING = 2
MSG_TYPE_VERSION_RESPONSE = 3
MSG_TYPE_STATE = 101
MSG_TYPE_RANK_UPDATE = 102
MSG_TYPE_CHAIN_UPDATE = 103
MSG_TYPE_PONG = 104
MSG_TYPE_ACHIEVEMENT = 105
MSG_TYPE_SESSION = 106
MSG_TYPE_GAME_EVENT = 107
MSG_TYPE_ERROR = 108
MSG_TYPE_VERSION_MISMATCH = 109
MSG_TYPE_ONLINE_USERS = 110

router = APIRouter(prefix="")


@dataclass
class ConnectionInfo:
    websocket: WebSocket
    user_id: str
    username: str
    avatar_url: str
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_admin: bool = False


class ConnectionManager:
    """Manages WebSocket connections keyed by guild_id."""

    def __init__(self) -> None:
        self.active_connections: dict[int, list[ConnectionInfo]] = defaultdict(list)

    async def connect(
        self, websocket: WebSocket, guild_id: int, user_id: str = "0",
        username: str = "Unknown", avatar_url: str = "", is_admin: bool = False,
    ) -> None:
        await websocket.accept()
        info = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            username=username,
            avatar_url=avatar_url,
            connected_at=datetime.now(UTC),
            is_admin=is_admin,
        )
        self.active_connections[guild_id].append(info)
        log.info(
            "WebSocket connected for guild %d (total: %d)",
            guild_id,
            len(self.active_connections[guild_id]),
        )

    def disconnect(self, websocket: WebSocket, guild_id: int) -> None:
        self.active_connections[guild_id] = [
            c for c in self.active_connections[guild_id] if c.websocket != websocket
        ]
        log.info(
            "WebSocket disconnected for guild %d (remaining: %d)",
            guild_id,
            len(self.active_connections[guild_id]),
        )

    async def broadcast(self, guild_id: int, message: bytes) -> None:
        disconnected = []
        for conn in self.active_connections[guild_id]:
            try:
                await conn.websocket.send_bytes(message)
            except Exception:
                disconnected.append(conn.websocket)
        for ws in disconnected:
            self.disconnect(ws, guild_id)

    async def broadcast_json(self, guild_id: int, message: dict) -> None:
        packed = msgpack.packb(message, use_single_float=True)
        await self.broadcast(guild_id, packed)

    async def broadcast_to_admins(self, guild_id: int, message: bytes) -> None:
        disconnected = []
        for conn in self.active_connections[guild_id]:
            if not conn.is_admin:
                continue
            try:
                await conn.websocket.send_bytes(message)
            except Exception:
                disconnected.append(conn.websocket)
        for ws in disconnected:
            self.disconnect(ws, guild_id)

    def get_online_users(self, guild_id: int) -> list[dict]:
        conns = self.active_connections.get(guild_id, [])
        dedup: dict[str, ConnectionInfo] = {}
        for conn in conns:
            uid = conn.user_id
            if uid not in dedup or conn.connected_at < dedup[uid].connected_at:
                dedup[uid] = conn
        return [
            {
                "user_id": uid,
                "username": info.username,
                "avatar_url": info.avatar_url,
                "connected_at": info.connected_at.isoformat(),
            }
            for uid, info in dedup.items()
        ]


manager = ConnectionManager()


async def get_board_state(session: AsyncSession, guild_id: int, guild_name: str) -> dict:
    """Fetch current board state as a dict for WebSocket and HTTP clients."""
    from sqlalchemy import select

    from stankbot.db.repositories import altars as altars_repo
    from stankbot.db.repositories import player_chain_totals as pct_repo
    from stankbot.db.repositories import player_totals as pt_repo
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

    session_svc = SessionService(session)
    session_id = await session_svc.current(guild_id)
    live_chain = await chains_repo.current_chain(session, guild_id, altar.id)

    # Session-level per-user counters from player_totals
    per_user_reactions_session: dict = {}
    per_user_stanks_session: dict = {}
    if session_id is not None:
        stmt = (
            select(pt_repo.PlayerTotal)
            .where(
                pt_repo.PlayerTotal.guild_id == guild_id,
                pt_repo.PlayerTotal.session_id == session_id,
            )
        )
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            uid = int(r.user_id)
            per_user_reactions_session[uid] = r.reactions_in_session
            per_user_stanks_session[uid] = r.stanks_in_session

    # Chain-level per-user counters from player_chain_totals
    per_user_reactions_chain: dict = {}
    per_user_stanks_chain: dict = {}
    if live_chain is not None:
        chain_totals = await pct_repo.get_for_chain(session, guild_id, live_chain.id)
        for uid, r in chain_totals.items():
            per_user_reactions_chain[uid] = r.reactions_in_chain
            per_user_stanks_chain[uid] = r.stanks_in_chain

    # Total session reactions for the tile (fallback to events table if needed)
    session_reactions = (
        await reaction_awards_repo.count_for_session(session, guild_id=guild_id, session_id=session_id)
        if session_id is not None else 0
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
    guild_id = session.get("guild_id") or session.get("guild") or session.get("active_guild_id")
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

        owner_id = int(getattr(config, "owner_id", 0) or 0)
        if int(user.get("id", 0)) != owner_id:
            from stankbot.web.tools import fetch_guild_member
            member = await fetch_guild_member(config, guild_id, int(user["id"]))
            if member is None:
                await websocket.close(code=4003, reason="Not in guild")
                return

    user_data = session.get("user", {}) or {}
    user_id_str = str(user_data.get("id", "0"))
    username = str(user_data.get("username", "Unknown"))
    avatar_url = str(user_data.get("avatar") or "")

    is_admin = False
    if is_dev_mock:
        is_admin = bool(session.get("is_global_admin", False) or session.get("is_guild_admin", False))
    else:
        if user_id_str != "0" and owner_id:
            try:
                from stankbot.db.engine import session_scope
                from stankbot.services.permission_service import PermissionService
                async with session_scope(session_factory) as db:
                    svc = PermissionService(db, owner_id=owner_id)
                    is_admin = await svc.is_global_admin(int(user_id_str))
            except Exception:
                log.warning("Failed to check admin status for WS client: user_id=%s", user_id_str)

    await manager.connect(websocket, guild_id, user_id=user_id_str, username=username, avatar_url=avatar_url, is_admin=is_admin)

    async def _broadcast_online_users(gid: int) -> None:
        users = manager.get_online_users(gid)
        log.info("_broadcast_online_users: guild=%d users=%s admin_count=%d", gid, users, sum(1 for c in manager.active_connections.get(gid, []) if c.is_admin))
        packed = msgpack.packb({"t": MSG_TYPE_ONLINE_USERS, "d": {"users": users}}, use_single_float=True)
        await manager.broadcast_to_admins(gid, packed)

    await _broadcast_online_users(guild_id)

    try:
        from stankbot.db.engine import session_scope
        from stankbot.web.tools import guild_name_for

        async with session_scope(session_factory) as db:
            guild_name = await guild_name_for(db, guild_id)
            state = await get_board_state(db, guild_id, guild_name)
        if state:
            state["version"] = getattr(app_state, "app_version", "0.0.0")
            packed = msgpack.packb({"t": MSG_TYPE_STATE, "d": state}, use_single_float=True)
            await websocket.send_bytes(packed)
    except Exception as e:
        log.warning("Failed to send initial state to WS client: %s", e)

    try:
        while True:
            try:
                data = await websocket.receive_bytes()
                msg = msgpack.unpackb(data, raw=False)
                msg_type = msg.get("t")
                if msg_type == MSG_TYPE_PING:
                    await websocket.send_bytes(msgpack.packb({"t": MSG_TYPE_PONG}))
                elif msg_type == MSG_TYPE_VERSION_RESPONSE:
                    client_version = msg.get("d", {}).get("version", "")
                    server_version = getattr(app_state, "app_version", "0.0.0")
                    if client_version != server_version:
                        await websocket.send_bytes(
                            msgpack.packb(
                                {"t": MSG_TYPE_VERSION_MISMATCH, "d": {"server_version": server_version, "client_version": client_version}},
                                use_single_float=True,
                            )
                        )
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.error("WebSocket error: %s", e)
                break
    finally:
        manager.disconnect(websocket, guild_id)
        await _broadcast_online_users(guild_id)


# ---------------------------------------------------------------------------
# Broadcast helpers — called from cogs and the mock event bridge
# ---------------------------------------------------------------------------


async def notify_chain_update(
    guild_id: int, current: int, current_unique: int, starter_user_id: int | None
) -> None:
    await manager.broadcast_json(
        guild_id,
        {
            "t": MSG_TYPE_CHAIN_UPDATE,
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
    await manager.broadcast_json(guild_id, {"t": MSG_TYPE_RANK_UPDATE, "d": payload})


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
        {"t": MSG_TYPE_ACHIEVEMENT, "d": {"user_id": str(user_id), "badge": badge}},
    )


def has_active_connections(guild_id: int) -> bool:
    """Return True if at least one WS client is connected for this guild."""
    return bool(manager.active_connections.get(guild_id))


async def broadcast_game_event(guild_id: int, event_id: int, event_type: str, user_id: int | None,
                                user_name: str | None, delta: int, reason: str | None,
                                created_at: str | None = None) -> None:
    """Broadcast a single game event to all WS clients for the guild."""
    entry: dict = {
        "id": event_id,
        "type": event_type,
        "user_id": str(user_id) if user_id else None,
        "user_name": user_name,
        "delta": delta,
        "reason": reason,
        "created_at": created_at,
    }
    await manager.broadcast_json(guild_id, {"t": MSG_TYPE_GAME_EVENT, "d": entry})


async def notify_session(
    guild_id: int, session_id: int, action: str, started_at: datetime, ended_at: datetime | None
) -> None:
    await manager.broadcast_json(
        guild_id,
        {
            "t": MSG_TYPE_SESSION,
            "d": {
                "session_id": session_id,
                "action": action,
                "started_at": started_at.isoformat() if started_at else None,
                "ended_at": ended_at.isoformat() if ended_at else None,
            },
        },
    )
