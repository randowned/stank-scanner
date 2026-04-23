"""Tests for v2_app WebSocket and API functionality."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stankbot.db.models import (
    Altar,
    Chain,
    ChainMessage,
    Guild,
    Player,
)
from stankbot.web.v2_app import (
    ConnectionManager,
    get_board_state,
    manager,
)


class MsgType:
    SUBSCRIBE = 1
    PING = 2
    STATE = 101
    RANK_UPDATE = 102
    CHAIN_UPDATE = 103
    PONG = 104
    ACHIEVEMENT = 105
    SESSION = 106
    ERROR = 107


class TestConnectionManager:
    @pytest.fixture
    def cm(self) -> ConnectionManager:
        return ConnectionManager()

    def test_initial_state(self, cm: ConnectionManager) -> None:
        assert cm.active_connections == {}

    @pytest.mark.asyncio
    async def test_connect_adds_connection(self, cm: ConnectionManager) -> None:
        ws = AsyncMock()
        ws.accept = AsyncMock()

        await cm.connect(ws, 123)

        assert 123 in cm.active_connections
        assert ws in cm.active_connections[123]
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, cm: ConnectionManager) -> None:
        ws = AsyncMock()
        cm.active_connections[123].append(ws)

        cm.disconnect(ws, 123)

        assert ws not in cm.active_connections[123]

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, cm: ConnectionManager) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        cm.active_connections[123].append(ws1)
        cm.active_connections[123].append(ws2)

        await cm.broadcast(123, b"test")

        ws1.send_bytes.assert_called_once_with(b"test")
        ws2.send_bytes.assert_called_once_with(b"test")


class TestMessageTypes:
    def test_msgtype_values(self) -> None:
        assert MsgType.SUBSCRIBE == 1
        assert MsgType.PING == 2
        assert MsgType.STATE == 101
        assert MsgType.RANK_UPDATE == 102
        assert MsgType.CHAIN_UPDATE == 103
        assert MsgType.PONG == 104
        assert MsgType.ACHIEVEMENT == 105
        assert MsgType.SESSION == 106
        assert MsgType.ERROR == 107


class TestBroadcastFunctions:
    @pytest.mark.asyncio
    async def test_notify_chain_update(self) -> None:
        with patch.object(manager, 'broadcast_json', new_callable=AsyncMock) as mock:
            from stankbot.web.v2_app import notify_chain_update
            await notify_chain_update(123, 50, 10, 456)
            mock.assert_called_once()
            call_args = mock.call_args[0]
            assert call_args[0] == 123
            assert call_args[1]["t"] == 103
            assert call_args[1]["d"]["current"] == 50

    @pytest.mark.asyncio
    async def test_notify_rank_update(self) -> None:
        with patch.object(manager, 'broadcast_json', new_callable=AsyncMock) as mock:
            from stankbot.web.v2_app import notify_rank_update
            rankings = [{"user_id": 1, "display_name": "Test", "earned_sp": 100, "punishments": 0}]
            await notify_rank_update(123, rankings)
            mock.assert_called_once()
            call_args = mock.call_args[0]
            assert call_args[0] == 123
            assert call_args[1]["t"] == 102

    @pytest.mark.asyncio
    async def test_notify_achievement(self) -> None:
        with patch.object(manager, 'broadcast_json', new_callable=AsyncMock) as mock:
            from stankbot.web.v2_app import notify_achievement
            badge = {"key": "first_stank", "name": "First Stank", "icon": "✨"}
            await notify_achievement(123, 456, badge)
            mock.assert_called_once()
            call_args = mock.call_args[0]
            assert call_args[0] == 123
            assert call_args[1]["t"] == 105

    @pytest.mark.asyncio
    async def test_notify_session(self) -> None:
        with patch.object(manager, 'broadcast_json', new_callable=AsyncMock) as mock:
            from datetime import datetime

            from stankbot.web.v2_app import notify_session
            await notify_session(123, 1, "start", datetime.now(UTC), None)
            mock.assert_called_once()
            call_args = mock.call_args[0]
            assert call_args[0] == 123
            assert call_args[1]["t"] == 106


@pytest.mark.usefixtures("session")
class TestGetBoardState:
    @pytest.mark.asyncio
    async def test_get_board_state_empty(self, session) -> None:
        result = await get_board_state(session, 123, "Test Server")
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_board_state_with_guild_and_altar(self, session) -> None:
        guild = Guild(id=123, name="Test Server")
        session.add(guild)
        altar = Altar(
            id=1,
            guild_id=123,
            channel_id=999,
            sticker_id=123456789,
            sticker_name_pattern="stank",
            display_name="main",
        )
        session.add(altar)
        player = Player(guild_id=123, user_id=456, display_name="TestPlayer")
        session.add(player)
        await session.commit()

        result = await get_board_state(session, 123, "Test Server")
        assert result["guild_name"] == "Test Server"
        assert "rankings" in result
        assert result["current"] == 0

    @pytest.mark.asyncio
    async def test_get_board_state_with_chain(self, session) -> None:
        guild = Guild(id=123, name="Test Server")
        session.add(guild)
        altar = Altar(
            id=1,
            guild_id=123,
            channel_id=999,
            sticker_id=123456789,
            sticker_name_pattern="stank",
            display_name="main",
        )
        session.add(altar)
        player1 = Player(guild_id=123, user_id=1, display_name="Starter")
        player2 = Player(guild_id=123, user_id=2, display_name="Second")
        session.add_all([player1, player2])
        await session.commit()

        now = datetime.now(UTC)
        chain = Chain(
            id=1,
            guild_id=123,
            altar_id=1,
            starter_user_id=1,
            started_at=now,
            session_id=1,
        )
        session.add(chain)

        chain_msg1 = ChainMessage(
            chain_id=1,
            user_id=1,
            message_id=111,
            position=1,
            created_at=now,
        )
        chain_msg2 = ChainMessage(
            chain_id=1,
            user_id=2,
            message_id=222,
            position=2,
            created_at=now,
        )
        session.add_all([chain_msg1, chain_msg2])
        await session.commit()

        result = await get_board_state(session, 123, "Test Server")
        assert result["current"] == 2
        assert result["chain_starter"]["user_id"] == 1


class TestConnectionManagerCleanup:
    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all_guilds(self) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()

        cm = ConnectionManager()
        await cm.connect(ws1, 123)
        await cm.connect(ws2, 456)

        assert len(cm.active_connections[123]) == 1
        assert len(cm.active_connections[456]) == 1

        cm.disconnect(ws1, 123)
        assert len(cm.active_connections[123]) == 0
        assert len(cm.active_connections[456]) == 1

        cm.disconnect(ws2, 456)
        assert len(cm.active_connections[456]) == 0

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()

        cm = ConnectionManager()
        await cm.connect(ws1, 123)
        await cm.connect(ws2, 123)

        ws1.send_bytes.side_effect = Exception("Connection lost")

        await cm.broadcast(123, b"test")

        ws1.send_bytes.assert_called_once()
        assert ws2.send_bytes.call_count == 1
        assert len(cm.active_connections[123]) == 1
