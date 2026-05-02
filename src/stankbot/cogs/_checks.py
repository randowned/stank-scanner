"""Slash-command permission checks.

``requires_admin()`` is an ``app_commands.check`` decorator that gates
admin commands behind ``PermissionService.is_admin``. Failed checks
raise ``MissingPermissions`` so the bot's central error handler can
reply ephemerally with a friendly message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from sqlalchemy import select

from stankbot.db.models import ChannelBinding, ChannelPurpose
from stankbot.services.permission_service import PermissionService

if TYPE_CHECKING:
    from stankbot.bot import StankBot


class WrongChannel(app_commands.CheckFailure):
    """Raised when a slash command is invoked outside an announcement channel."""

    def __init__(self, allowed_channel_ids: list[int]) -> None:
        self.allowed_channel_ids = allowed_channel_ids
        super().__init__("command must be used in an announcement channel")


class SilentlySuppressed(app_commands.CheckFailure):
    """Maintenance-mode gate: the interaction was silently ACK'd and
    discarded. The error handler must NOT send any follow-up.
    """


async def is_interaction_admin(interaction: discord.Interaction) -> bool:
    """Resolve admin status for the interaction's invoker."""
    if interaction.guild is None:
        return False
    bot: StankBot = interaction.client  # type: ignore[assignment]
    member = interaction.user
    roles = [r.id for r in getattr(member, "roles", [])]
    perms = getattr(member, "guild_permissions", None)
    has_manage_guild = bool(perms and perms.manage_guild)
    async with bot.db() as session:
        svc = PermissionService(session, owner_id=bot.config.owner_id)
        return await svc.is_admin(
            interaction.guild.id,
            member.id,
            roles,
            has_manage_guild=has_manage_guild,
        )


async def maintenance_mode_enabled(bot: StankBot, guild_id: int) -> bool:
    from stankbot.services.settings_service import Keys, SettingsService

    async with bot.db() as session:
        return bool(
            await SettingsService(session).get(guild_id, Keys.MAINTENANCE_MODE, False)
        )


async def silently_suppress(interaction: discord.Interaction) -> None:
    """ACK and delete the interaction response so the user sees nothing."""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        await interaction.delete_original_response()
    except discord.DiscordException:
        pass


def requires_admin() -> app_commands.check:  # type: ignore[type-arg]
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        bot: StankBot = interaction.client  # type: ignore[assignment]
        member = interaction.user
        roles = [r.id for r in getattr(member, "roles", [])]
        perms = getattr(member, "guild_permissions", None)
        has_manage_guild = bool(perms and perms.manage_guild)

        async with bot.db() as session:
            svc = PermissionService(session, owner_id=bot.config.owner_id)
            return await svc.is_admin(
                interaction.guild.id,
                member.id,
                roles,
                has_manage_guild=has_manage_guild,
            )

    return app_commands.check(predicate)


def requires_stats_access() -> app_commands.check:  # type: ignore[type-arg]
    """Allow everyone by default; admin-only if guild setting enabled."""

    async def predicate(interaction: discord.Interaction) -> bool:
        from stankbot.services.settings_service import Keys, SettingsService

        if interaction.guild is None:
            return False
        bot: StankBot = interaction.client  # type: ignore[assignment]
        async with bot.db() as session:
            admin_only = await SettingsService(session).get(
                interaction.guild.id, Keys.MEDIA_REPLIES_ADMIN_ONLY, False
            )
        if not admin_only:
            return True
        return await is_interaction_admin(interaction)

    return app_commands.check(predicate)


def requires_announcement_channel() -> app_commands.check:  # type: ignore[type-arg]
    """Restrict a slash command to channels wired as ``announcements``.

    If no announcement channels are configured for the guild, the command
    is allowed anywhere (bootstrapping). Raises ``WrongChannel`` otherwise.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.channel is None:
            return True
        bot: StankBot = interaction.client  # type: ignore[assignment]
        async with bot.db() as session:
            rows = await session.execute(
                select(ChannelBinding.channel_id).where(
                    ChannelBinding.guild_id == interaction.guild.id,
                    ChannelBinding.purpose == ChannelPurpose.ANNOUNCEMENTS.value,
                )
            )
            allowed = [int(r) for r in rows.scalars()]
        if not allowed:
            return True
        if interaction.channel.id in allowed:
            return True
        raise WrongChannel(allowed)

    return app_commands.check(predicate)
