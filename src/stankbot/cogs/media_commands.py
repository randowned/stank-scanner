"""Discord commands to display media item stats via embed templates.

Usage::

    /media youtube info <slug>
    /media spotify info <slug>
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from stankbot.bot import StankBot
from stankbot.db.repositories import media as media_repo
from stankbot.services.embed_builders import build_media_embed
from stankbot.services.settings_service import Keys, SettingsService

log = logging.getLogger(__name__)


class MediaCommands(commands.GroupCog, name="media"):
    """``/media`` commands — show stats for tracked YouTube / Spotify items."""

    def __init__(self, bot: StankBot) -> None:
        self.bot = bot
        super().__init__()

    youtube = app_commands.Group(
        name="youtube", description="Show YouTube media stats."
    )
    spotify = app_commands.Group(
        name="spotify", description="Show Spotify media stats."
    )

    async def _send_media_embed(
        self,
        interaction: discord.Interaction,
        media_type: str,
        slug: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works inside a server.", ephemeral=True
            )
            return

        async with self.bot.db() as session:
            settings = SettingsService(session)
            ephemeral = bool(
                await settings.get(
                    interaction.guild.id,
                    Keys.MEDIA_REPLIES_EPHEMERAL,
                    True,
                )
            )

            await interaction.response.defer(thinking=True, ephemeral=ephemeral)

            item = await media_repo.get_by_slug(
                session, interaction.guild.id, media_type, slug
            )
            if item is None:
                await interaction.followup.send(
                    f"No {media_type} item found with slug `{slug}`.", ephemeral=True
                )
                return

            metrics_raw = await media_repo.get_metric_cache(session, item.id)
            metrics: dict[str, str | int] = {}
            for key, val in metrics_raw.items():
                if isinstance(val, dict) and "value" in val:
                    metrics[key] = int(val["value"])
            metrics["external_id"] = item.external_id

            last_fetched = (
                item.metrics_last_fetched_at.isoformat()
                if item.metrics_last_fetched_at
                else None
            )

            embed = await build_media_embed(
                media_type=media_type,
                title=item.title,
                channel_name=item.channel_name,
                slug=item.slug,
                thumbnail_url=item.thumbnail_url,
                published_at=item.published_at.isoformat() if item.published_at else None,
                duration_seconds=item.duration_seconds,
                metrics=metrics,
                last_fetched_at=last_fetched,
                guild_id=interaction.guild.id,
                session=session,
            )

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    @youtube.command(name="info", description="Show stats for a tracked YouTube video.")
    @app_commands.describe(slug="The video's slug (short name).")
    async def youtube_info(
        self,
        interaction: discord.Interaction,
        slug: str,
    ) -> None:
        await self._send_media_embed(interaction, "youtube", slug)

    @spotify.command(name="info", description="Show stats for a tracked Spotify item.")
    @app_commands.describe(slug="The track or album slug.")
    async def spotify_info(
        self,
        interaction: discord.Interaction,
        slug: str,
    ) -> None:
        await self._send_media_embed(interaction, "spotify", slug)


async def setup(bot: StankBot) -> None:
    await bot.add_cog(MediaCommands(bot))
