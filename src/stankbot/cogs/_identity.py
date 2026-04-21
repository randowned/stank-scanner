"""Identity helpers — resolve a Discord user's display name and
upsert the ``Player`` row so future renders don't fall back to the raw
numeric ID.

Used wherever we persist work for a user who may not have sent a
message (e.g. reaction-only contributors, /stank points on an uncached
target). Callers that already have a ``Member`` / ``User`` should pass
it as ``hint`` to avoid an extra API call.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.repositories import players as players_repo

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)


def _name_from(obj: object) -> str | None:
    if obj is None:
        return None
    name = getattr(obj, "display_name", None) or getattr(obj, "name", None)
    return name or None


async def resolve_display_name(
    bot: StankBot,
    *,
    guild_id: int,
    user_id: int,
    hint: discord.Member | discord.User | None = None,
) -> str | None:
    """Best-effort resolve a display name for ``user_id``.

    Order: hint → guild cache → guild fetch → global user fetch. Never
    raises — returns ``None`` if every lookup fails.
    """
    name = _name_from(hint)
    if name:
        return name

    guild = bot.get_guild(guild_id)
    if guild is not None:
        member = guild.get_member(user_id)
        name = _name_from(member)
        if name:
            return name
        try:
            member = await guild.fetch_member(user_id)
            name = _name_from(member)
            if name:
                return name
        except discord.DiscordException:
            pass

    cached = bot.get_user(user_id)
    name = _name_from(cached)
    if name:
        return name
    try:
        user = await bot.fetch_user(user_id)
        return _name_from(user)
    except discord.DiscordException:
        return None


async def ensure_player(
    session: AsyncSession,
    bot: StankBot,
    *,
    guild_id: int,
    user_id: int,
    hint: discord.Member | discord.User | None = None,
) -> str:
    """Upsert the ``Player`` row, fetching a display name from Discord
    if one isn't cached locally. Returns the name (or ``str(user_id)``
    if every lookup failed).
    """
    name = await resolve_display_name(
        bot, guild_id=guild_id, user_id=user_id, hint=hint
    )
    await players_repo.get_or_create(session, guild_id, user_id, name)
    return name or str(user_id)
