"""Member-sync cog — keeps guild_member_roles table in sync with Discord.

Only touches members who already have a row in ``guild_member_roles``
(inserted on first interaction via ``fetch_guild_member``). Unknown
members are silently skipped — their data is not stored.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from stankbot.db.models import GuildMember

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)


class MemberSync(commands.Cog):
    def __init__(self, bot: StankBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild_id = after.guild.id
        user_id = after.id
        async with self.bot.db() as session:
            row = await session.get(GuildMember, (guild_id, user_id))
            if row is None:
                return
            row.role_ids = [r.id for r in after.roles]
            row.permissions = after.guild_permissions.value
            row.nick = after.nick
            row.username = after.name
            row.global_name = getattr(after, "global_name", None)
            row.avatar = after.avatar.key if after.avatar else None

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild_id = member.guild.id
        user_id = member.id
        async with self.bot.db() as session:
            row = await session.get(GuildMember, (guild_id, user_id))
            if row is None:
                return
            await session.delete(row)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        pass


async def setup(bot: StankBot) -> None:
    await bot.add_cog(MemberSync(bot))
