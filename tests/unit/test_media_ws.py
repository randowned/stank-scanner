"""Unit tests for WebSocket media milestone broadcast."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from stankbot.web.ws import MSG_TYPE_MEDIA_MILESTONE, broadcast_media_milestone


@pytest.mark.asyncio
async def test_broadcast_media_milestone_message_shape() -> None:
    """The WS message has correct t (type) and d (data) fields."""
    with patch("stankbot.web.ws.manager") as mock_mgr:
        mock_mgr.broadcast_json = AsyncMock()

        await broadcast_media_milestone(
            guild_id=7,
            media_item_id=1,
            media_type="youtube",
            metric_key="view_count",
            milestone_value=1_000_000,
            new_value=1_000_123,
            title="Test Video",
            channel_name="Test Channel",
            thumbnail_url="https://example.com/thumb.jpg",
            name="test-video",
            external_id="vid_001",
        )

        mock_mgr.broadcast_json.assert_awaited_once()
        args, _ = mock_mgr.broadcast_json.call_args
        assert args[0] == 7
        msg = args[1]
        assert "t" in msg
        assert msg["t"] == MSG_TYPE_MEDIA_MILESTONE
        assert msg["d"]["media_item_id"] == 1
        assert msg["d"]["media_type"] == "youtube"
        assert msg["d"]["metric_key"] == "view_count"
        assert msg["d"]["milestone_value"] == 1_000_000
        assert msg["d"]["new_value"] == 1_000_123
        assert msg["d"]["title"] == "Test Video"
        assert msg["d"]["channel_name"] == "Test Channel"
        assert msg["d"]["thumbnail_url"] == "https://example.com/thumb.jpg"
        assert msg["d"]["name"] == "test-video"
        assert msg["d"]["external_id"] == "vid_001"


@pytest.mark.asyncio
async def test_broadcast_media_milestone_nullable_fields() -> None:
    """Optional fields (channel_name, thumbnail_url, name) can be None."""
    with patch("stankbot.web.ws.manager") as mock_mgr:
        mock_mgr.broadcast_json = AsyncMock()

        await broadcast_media_milestone(
            guild_id=7,
            media_item_id=2,
            media_type="spotify",
            metric_key="playcount",
            milestone_value=5_000_000,
            new_value=5_000_500,
            title="Test Track",
            channel_name=None,
            thumbnail_url=None,
            name=None,
            external_id="sid_001",
        )

        mock_mgr.broadcast_json.assert_awaited_once()
        args, _ = mock_mgr.broadcast_json.call_args
        msg = args[1]
        assert msg["d"]["channel_name"] is None
        assert msg["d"]["thumbnail_url"] is None
        assert msg["d"]["name"] is None
