"""Discord commands to display media item stats via embed templates.

Usage::

    /stats youtube info <name>
    /stats spotify info <name>
    /stats youtube chart <name> <type> <range>
    /stats spotify chart <name> <type> <range>
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from stankbot.cogs._checks import is_interaction_admin, requires_stats_access
from stankbot.db.repositories import media as media_repo
from stankbot.services.embed_builders import build_media_embed
from stankbot.services.settings_service import Keys, SettingsService

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)

YOUTUBE_TYPE_CHOICES = [
    app_commands.Choice(name="Views", value="view_count"),
    app_commands.Choice(name="Likes", value="like_count"),
    app_commands.Choice(name="Comments", value="comment_count"),
]

SPOTIFY_TYPE_CHOICES = [
    app_commands.Choice(name="Popularity", value="popularity"),
]

RANGE_CHOICES = [
    app_commands.Choice(name="6 hours", value="6h"),
    app_commands.Choice(name="12 hours", value="12h"),
    app_commands.Choice(name="1 day", value="24h"),
    app_commands.Choice(name="1 week", value="7d"),
    app_commands.Choice(name="1 month", value="30d"),
    app_commands.Choice(name="90 days", value="90d"),
    app_commands.Choice(name="1 year", value="365d"),
    app_commands.Choice(name="All time", value="all"),
]

AGGREGATION_CHOICES = [
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="Minutely", value="minutely"),
    app_commands.Choice(name="Hourly", value="hourly"),
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly"),
    app_commands.Choice(name="Monthly", value="monthly"),
]


class StatsCommands(commands.GroupCog, name="stats"):
    """``/stats`` commands — show metrics for tracked YouTube / Spotify items."""

    def __init__(self, bot: StankBot) -> None:
        self.bot = bot
        super().__init__()

    youtube = app_commands.Group(
        name="youtube", description="YouTube media stats."
    )
    spotify = app_commands.Group(
        name="spotify", description="Spotify media stats."
    )

    # ------------------------------------------------------------------
    # Autocomplete helper
    # ------------------------------------------------------------------

    async def _slug_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        media_type: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        async with self.bot.db() as session:
            items = await media_repo.list_all(
                session, interaction.guild.id, media_type
            )
        choices: list[app_commands.Choice[str]] = []
        for it in items:
            if not it.name:
                continue
            if current.lower() in it.name.lower():
                choices.append(
                    app_commands.Choice(name=it.name, value=it.name)
                )
                if len(choices) >= 25:
                    break
        return choices

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def _send_info_embed(
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
            enabled = await settings.get(
                interaction.guild.id, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"]
            )
            is_admin = await is_interaction_admin(interaction)
            if media_type not in enabled and not is_admin:
                await interaction.response.send_message(
                    f"{media_type.capitalize()} stats are currently disabled.", ephemeral=True
                )
                return
            settings = SettingsService(session)
            ephemeral = bool(
                await settings.get(
                    interaction.guild.id,
                    Keys.MEDIA_REPLIES_EPHEMERAL,
                    True,
                )
            )

            await interaction.response.defer(thinking=True, ephemeral=ephemeral)

            item = await media_repo.get_by_name(
                session, interaction.guild.id, media_type, slug
            )
            if item is None:
                await interaction.followup.send(
                    f"No {media_type} item found with name `{slug}`.",
                    ephemeral=True,
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
                media_item_id=item.id,
                title=item.title,
                channel_name=item.channel_name,
                name=item.name,
                thumbnail_url=item.thumbnail_url,
                published_at=item.published_at.isoformat() if item.published_at else None,
                duration_seconds=item.duration_seconds,
                metrics=metrics,
                last_fetched_at=last_fetched,
                guild_id=interaction.guild.id,
                session=session,
            )

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    async def _send_chart_embed(
        self,
        interaction: discord.Interaction,
        media_type: str,
        slug: str,
        metric: str,
        range_value: str,
        aggregation: str = "auto",
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        async with self.bot.db() as session:
            item = await media_repo.get_by_name(
                session, interaction.guild.id, media_type, slug
            )
            if item is None:
                await interaction.followup.send(
                    f"No {media_type} item found with name `{slug}`.",
                    ephemeral=True,
                )
                return

            base_url = self.bot.config.oauth_redirect_uri.rsplit("/", 2)[0]
            date_param = datetime.now(UTC).isoformat().replace("+", "%2B")
            url = (
                f"{base_url}/api/media/{item.id}/chart"
                f"?metric={metric}&date={date_param}"
            )

            if range_value == "all":
                url += "&days=0"
            elif range_value.endswith("h"):
                url += f"&hours={range_value[:-1]}"
            else:
                url += f"&days={range_value[:-1]}"

            if aggregation != "auto":
                url += f"&agg={aggregation}"

            embed = discord.Embed(
                title=item.title,
                description=f"{media_type.capitalize()} · {metric} · {range_value}",
                color=discord.Color.blurple(),
            )
            embed.set_image(url=url)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # YouTube info
    # ------------------------------------------------------------------

    @youtube.command(name="info", description="Show stats for a tracked YouTube video.")
    @app_commands.describe(slug="The video's slug (short name).")
    @app_commands.rename(slug="name")
    @requires_stats_access()
    async def youtube_info(
        self,
        interaction: discord.Interaction,
        slug: str,
    ) -> None:
        await self._send_info_embed(interaction, "youtube", slug)

    @youtube_info.autocomplete("slug")
    async def _youtube_info_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._slug_autocomplete(interaction, current, "youtube")

    # ------------------------------------------------------------------
    # Spotify info
    # ------------------------------------------------------------------

    @spotify.command(name="info", description="Show stats for a tracked Spotify item.")
    @app_commands.describe(slug="The track or album slug.")
    @app_commands.rename(slug="name")
    @requires_stats_access()
    async def spotify_info(
        self,
        interaction: discord.Interaction,
        slug: str,
    ) -> None:
        await self._send_info_embed(interaction, "spotify", slug)

    @spotify_info.autocomplete("slug")
    async def _spotify_info_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._slug_autocomplete(interaction, current, "spotify")

    # ------------------------------------------------------------------
    # YouTube chart
    # ------------------------------------------------------------------

    @youtube.command(name="chart", description="Chart a metric for a YouTube video.")
    @app_commands.describe(slug="The video's slug.", metric="Which metric to chart.", range_="Time range to show.", aggregation="Tick grouping.")
    @app_commands.choices(metric=YOUTUBE_TYPE_CHOICES, range_=RANGE_CHOICES, aggregation=AGGREGATION_CHOICES)
    @app_commands.rename(slug="name", metric="type", range_="range", aggregation="aggregation")
    @requires_stats_access()
    async def youtube_chart(
        self,
        interaction: discord.Interaction,
        slug: str,
        metric: str,
        range_: str,
        aggregation: str = "auto",
    ) -> None:
        await self._send_chart_embed(interaction, "youtube", slug, metric, range_, aggregation)

    @youtube_chart.autocomplete("slug")
    async def _youtube_chart_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._slug_autocomplete(interaction, current, "youtube")

    # ------------------------------------------------------------------
    # Spotify chart
    # ------------------------------------------------------------------

    @spotify.command(name="chart", description="Chart a metric for a Spotify item.")
    @app_commands.describe(slug="The track or album slug.", metric="Which metric to chart.", range_="Time range to show.", aggregation="Tick grouping.")
    @app_commands.choices(metric=SPOTIFY_TYPE_CHOICES, range_=RANGE_CHOICES, aggregation=AGGREGATION_CHOICES)
    @app_commands.rename(slug="name", metric="type", range_="range", aggregation="aggregation")
    @requires_stats_access()
    async def spotify_chart(
        self,
        interaction: discord.Interaction,
        slug: str,
        metric: str,
        range_: str,
        aggregation: str = "auto",
    ) -> None:
        await self._send_chart_embed(interaction, "spotify", slug, metric, range_, aggregation)

    @spotify_chart.autocomplete("slug")
    async def _spotify_chart_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._slug_autocomplete(interaction, current, "spotify")


async def setup(bot: StankBot) -> None:
    await bot.add_cog(StatsCommands(bot))
