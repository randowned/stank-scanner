"""Announcement service tests — broadcast_media_milestone edge cases."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import discord

from stankbot.db.models import ChannelBinding, ChannelPurpose, Guild
from stankbot.services.announcement_service import (
    broadcast_media_milestone,
)

# ── helpers ─────────────────────────────────────────────────────────────────


async def _add_announcement_channel(
    session: Any, guild_id: int, channel_id: int,
) -> None:
    session.add(ChannelBinding(
        guild_id=guild_id,
        channel_id=channel_id,
        purpose=ChannelPurpose.ANNOUNCEMENTS.value,
    ))


def _make_embed() -> discord.Embed:
    return discord.Embed(title="Test", color=discord.Color.gold())


# ── broadcast_media_milestone ───────────────────────────────────────────────


async def test_disabled_returns_empty(session: Any) -> None:
    """When toggle is False, skip entirely regardless of channels."""
    sender = AsyncMock()
    embed = _make_embed()

    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=False,
    )
    assert result == []
    sender.send_embed_to.assert_not_called()


async def test_no_channels_configured(session: Any) -> None:
    """No announcement channels, no media channel — send to nothing."""
    sender = AsyncMock()
    embed = _make_embed()

    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=True,
    )
    assert result == []
    sender.send_embed_to.assert_not_called()


async def test_sends_to_announcement_channels(session: Any) -> None:
    session.add(Guild(id=1))
    await _add_announcement_channel(session, 1, 10)
    await _add_announcement_channel(session, 1, 20)
    await session.flush()

    sender = AsyncMock()
    embed = _make_embed()

    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=True,
    )
    assert sorted(result) == [10, 20]
    assert sender.send_embed_to.call_count == 2


async def test_sends_to_media_channel(session: Any) -> None:
    """Media channel is additional — sent on top of (possibly empty) announcements."""
    session.add(Guild(id=1))
    await session.flush()

    sender = AsyncMock()
    embed = _make_embed()

    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=True,
        media_announce_channel_id=99,
    )
    assert result == [99]
    sender.send_embed_to.assert_called_once_with(99, embed)


async def test_sends_to_both_sources(session: Any) -> None:
    """Announcement channels + media channel — sends to both."""
    session.add(Guild(id=1))
    await _add_announcement_channel(session, 1, 10)
    await _add_announcement_channel(session, 1, 20)
    await session.flush()

    sender = AsyncMock()
    embed = _make_embed()

    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=True,
        media_announce_channel_id=99,
    )
    assert sorted(result) == [10, 20, 99]
    assert sender.send_embed_to.call_count == 3


async def test_deduplicates_overlapping_channel(session: Any) -> None:
    """If the media channel ID is also an announcement channel, send once."""
    session.add(Guild(id=1))
    await _add_announcement_channel(session, 1, 10)
    await _add_announcement_channel(session, 1, 20)
    await session.flush()

    sender = AsyncMock()
    embed = _make_embed()

    # media_channel=10 is already an announcement channel
    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=True,
        media_announce_channel_id=10,
    )
    assert sorted(result) == [10, 20]
    assert sender.send_embed_to.call_count == 2


async def test_different_guild_isolation(session: Any) -> None:
    """Announcement channels are scoped by guild_id."""
    session.add(Guild(id=1))
    session.add(Guild(id=2))
    await _add_announcement_channel(session, 1, 10)
    await _add_announcement_channel(session, 2, 30)
    await session.flush()

    sender = AsyncMock()
    embed = _make_embed()

    result = await broadcast_media_milestone(
        session, sender, guild_id=1, embed=embed,
        milestones_enabled=True,
    )
    assert result == [10]
    sender.send_embed_to.assert_called_once_with(10, embed)
