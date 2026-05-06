"""Announcement posting — resolves announcement channel bindings and
pushes embeds into them. Shared between the scheduler (session markers)
and the chain listener (record-broken notices, once wired).

No Discord imports here beyond the message-sending protocol — the
scheduler passes a ``Sender`` that the ``StankBot`` concrete class
fulfils. Tests can pass a fake.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol, runtime_checkable

import discord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import ChannelBinding, ChannelPurpose


@runtime_checkable
class EmbedSender(Protocol):
    async def send_embed_to(self, channel_id: int, embed: Any) -> None: ...


async def announcement_channel_ids(
    session: AsyncSession, guild_id: int
) -> list[int]:
    stmt = select(ChannelBinding.channel_id).where(
        ChannelBinding.guild_id == guild_id,
        ChannelBinding.purpose == ChannelPurpose.ANNOUNCEMENTS.value,
    )
    return list((await session.execute(stmt)).scalars().all())


async def broadcast(
    sender: EmbedSender,
    channel_ids: Iterable[int],
    embed: discord.Embed,
) -> None:
    for cid in channel_ids:
        await sender.send_embed_to(cid, embed)


async def broadcast_to_guild(
    session: AsyncSession,
    sender: EmbedSender,
    *,
    guild_id: int,
    embed: discord.Embed,
) -> Sequence[int]:
    """Fetch the guild's announcement channels + send. Returns the list
    of channel ids the embed was pushed to (possibly empty).
    """
    ids = await announcement_channel_ids(session, guild_id)
    await broadcast(sender, ids, embed)
    return ids


async def broadcast_media_milestone(
    session: AsyncSession,
    sender: EmbedSender,
    *,
    guild_id: int,
    embed: discord.Embed,
    media_announce_channel_id: int | None = None,
    milestones_enabled: bool = True,
) -> Sequence[int]:
    """Send a media milestone embed to announcement channels plus an
    optional dedicated media channel. Respects the milestones toggle.

    Returns the deduplicated set of channel IDs the embed was sent to.
    """
    if not milestones_enabled:
        return []
    seen: set[int] = set(await announcement_channel_ids(session, guild_id))
    if media_announce_channel_id is not None:
        seen.add(media_announce_channel_id)
    await broadcast(sender, seen, embed)
    return list(seen)
