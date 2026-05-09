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

from stankbot.cogs._checks import requires_stats_access
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
    app_commands.Choice(name="1 hour", value="1h"),
    app_commands.Choice(name="6 hours", value="6h"),
    app_commands.Choice(name="12 hours", value="12h"),
    app_commands.Choice(name="24 hours", value="24h"),
    app_commands.Choice(name="48 hours", value="48h"),
    app_commands.Choice(name="1 week", value="7d"),
    app_commands.Choice(name="1 month", value="30d"),
    app_commands.Choice(name="90 days", value="90d"),
    app_commands.Choice(name="1 year", value="365d"),
    app_commands.Choice(name="All time", value="all"),
]

MODE_CHOICES = [
    app_commands.Choice(name="Total (cumulative)", value="total"),
    app_commands.Choice(name="Delta (per-tick change)", value="delta"),
]

AGGREGATION_CHOICES = [
    app_commands.Choice(name="5 minutes", value="5min"),
    app_commands.Choice(name="15 minutes", value="15min"),
    app_commands.Choice(name="30 minutes", value="30min"),
    app_commands.Choice(name="Hourly", value="hourly"),
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly"),
    app_commands.Choice(name="Monthly", value="monthly"),
]

# Bucket size in minutes for each aggregation value
_BUCKET_MINUTES: dict[str, int] = {
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "hourly": 60,
    "daily": 1440,
    "weekly": 10080,
    "monthly": 43200,
}

# Range choice value → hours (0 = "all time")
_RANGE_HOURS: dict[str, float] = {
    "1h": 1,
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "48h": 48,
    "7d": 168,
    "30d": 720,
    "90d": 2160,
    "365d": 8760,
    "all": 0,
}

_PROVIDER_INTERVAL_KEYS_COG: dict[str, str] = {
    "youtube": Keys.MEDIA_YOUTUBE_UPDATE_INTERVAL_MINUTES,
    "spotify": Keys.MEDIA_SPOTIFY_UPDATE_INTERVAL_MINUTES,
}


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

    async def _name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        media_type: str,
        exclude_names: set[str] | None = None,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        exclude = exclude_names or set()
        async with self.bot.db() as session:
            settings = SettingsService(session)
            enabled = await settings.get(
                interaction.guild.id, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"]
            )
            if media_type not in enabled:
                return []
            items = await media_repo.list_all(
                session, interaction.guild.id, media_type
            )
        choices: list[app_commands.Choice[str]] = []
        for it in items:
            if not it.name or it.name in exclude:
                continue
            if current.lower() in it.name.lower():
                choices.append(
                    app_commands.Choice(name=it.name, value=it.name)
                )
                if len(choices) >= 25:
                    break
        return choices

    async def _aggregation_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        media_type: str,
    ) -> list[app_commands.Choice[str]]:
        interval_minutes = 60
        if interaction.guild is not None:
            interval_key = _PROVIDER_INTERVAL_KEYS_COG.get(media_type)
            if interval_key:
                async with self.bot.db() as session:
                    interval_minutes = await SettingsService(session).get(
                        interaction.guild.id, interval_key, 60
                    )

        # Read currently selected range from namespace if present
        range_val: str | None = getattr(interaction.namespace, "range", None)
        range_hours = _RANGE_HOURS.get(range_val, 0) if range_val else 0

        choices: list[app_commands.Choice[str]] = []
        for choice in AGGREGATION_CHOICES:
            bucket_min = _BUCKET_MINUTES.get(choice.value, 0)
            # Hide resolutions finer than the provider's configured poll interval
            if bucket_min < interval_minutes:
                continue
            # Hide resolutions that don't fit within the selected range (skip if "all" or unset)
            if range_hours > 0 and bucket_min * 60 >= range_hours * 3600:
                continue
            if current and current.lower() not in choice.name.lower():
                continue
            choices.append(choice)
        return choices

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def _send_info_embed(
        self,
        interaction: discord.Interaction,
        media_type: str,
        name: str,
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
            if media_type not in enabled:
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
                session, interaction.guild.id, media_type, name
            )
            if item is None:
                await interaction.followup.send(
                    f"No {media_type} item found with name `{name}`.",
                    ephemeral=True,
                )
                return

            metrics_raw = await media_repo.get_metric_cache(session, item.id)
            metrics: dict[str, str | int] = {}
            for key, val in metrics_raw.items():
                if isinstance(val, dict) and "value" in val:
                    metrics[key] = int(val["value"])
            metrics["external_id"] = item.external_id

            last_fetched = max(
                (
                    val["fetched_at"]
                    for val in metrics_raw.values()
                    if isinstance(val, dict) and val.get("fetched_at")
                ),
                default=None,
            )

            base_url = self.bot.config.oauth_redirect_uri.rsplit("/", 2)[0]

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
                base_url=base_url,
            )

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    async def _send_chart_embed(
        self,
        interaction: discord.Interaction,
        media_type: str,
        name: str,
        metric: str,
        range_value: str,
        mode: str = "total",
        aggregation: str | None = None,
        compare_names: list[str] | None = None,
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
            if media_type not in enabled:
                await interaction.response.send_message(
                    f"{media_type.capitalize()} stats are currently disabled.", ephemeral=True
                )
                return
            ephemeral = bool(
                await settings.get(
                    interaction.guild.id,
                    Keys.MEDIA_REPLIES_EPHEMERAL,
                    True,
                )
            )

        await interaction.response.defer(thinking=True, ephemeral=ephemeral)

        async with self.bot.db() as session:
            all_names = [name] + (compare_names or [])
            items = []
            missing: list[str] = []
            for n in all_names:
                it = await media_repo.get_by_name(session, interaction.guild.id, media_type, n)
                if it is None:
                    missing.append(n)
                else:
                    items.append(it)

            if missing:
                await interaction.followup.send(
                    f"No {media_type} item(s) found: {', '.join(f'`{m}`' for m in missing)}",
                    ephemeral=True,
                )
                return

            base_url = self.bot.config.oauth_redirect_uri.rsplit("/", 2)[0]

            if compare_names:
                compare_ids = ",".join(str(it.id) for it in items[1:])
                url = f"{base_url}/api/media/{items[0].id}/chart?metric={metric}&compare_ids={compare_ids}"
                if range_value == "all":
                    url += "&days=0"
                elif range_value.endswith("h"):
                    url += f"&hours={range_value[:-1]}"
                else:
                    url += f"&days={range_value[:-1]}"
                if mode != "total":
                    url += f"&mode={mode}"
                if aggregation:
                    url += f"&aggregation={aggregation}"
                title = " vs ".join(it.name or it.title for it in items)
                description = (
                    f"{media_type.capitalize()} · {metric} · {range_value} · {mode}"
                    + (f" · {aggregation}" if aggregation else "")
                )
                media_url = f"{base_url}/media/{items[0].id}?compare={compare_ids}&metric={metric}"
            else:
                item = items[0]
                url = f"{base_url}/api/media/{item.id}/chart?metric={metric}"
                if range_value == "all":
                    url += "&days=0"
                elif range_value.endswith("h"):
                    url += f"&hours={range_value[:-1]}"
                else:
                    url += f"&days={range_value[:-1]}"
                if mode != "total":
                    url += f"&mode={mode}"
                if aggregation:
                    url += f"&aggregation={aggregation}"
                title = item.title
                description = (
                    f"{media_type.capitalize()} · {metric} · {range_value} · {mode}"
                    + (f" · {aggregation}" if aggregation else "")
                )
                media_url = f"{base_url}/media/{item.id}"

            embed = discord.Embed(title=title, url=media_url, description=description, color=discord.Color.blurple())
            embed.set_image(url=url)

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    # ------------------------------------------------------------------
    # YouTube info
    # ------------------------------------------------------------------

    @youtube.command(name="info", description="Show stats for a tracked YouTube video.")
    @app_commands.describe(name="The video's name.")
    @requires_stats_access()
    async def youtube_info(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        await self._send_info_embed(interaction, "youtube", name)

    @youtube_info.autocomplete("name")
    async def _youtube_info_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current, "youtube")

    # ------------------------------------------------------------------
    # Spotify info
    # ------------------------------------------------------------------

    @spotify.command(name="info", description="Show stats for a tracked Spotify item.")
    @app_commands.describe(name="The track or album name.")
    @requires_stats_access()
    async def spotify_info(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        await self._send_info_embed(interaction, "spotify", name)

    @spotify_info.autocomplete("name")
    async def _spotify_info_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current, "spotify")

    # ------------------------------------------------------------------
    # YouTube chart
    # ------------------------------------------------------------------

    @youtube.command(name="chart", description="Chart a metric for a YouTube video.")
    @app_commands.describe(
        name="The video's name.",
        metric="Which metric to chart.",
        range_="Time range to show.",
        mode="Total values or per-tick delta.",
        aggregation="Bucket size for resolution.",
        compare1="A second video to compare.",
        compare2="A third video to compare.",
        compare3="A fourth video to compare.",
    )
    @app_commands.choices(metric=YOUTUBE_TYPE_CHOICES, range_=RANGE_CHOICES, mode=MODE_CHOICES)
    @app_commands.rename(metric="type", range_="range", aggregation="resolution")
    @requires_stats_access()
    async def youtube_chart(
        self,
        interaction: discord.Interaction,
        name: str,
        metric: str = "view_count",
        range_: str = "24h",
        mode: str = "delta",
        aggregation: str | None = "hourly",
        compare1: str | None = None,
        compare2: str | None = None,
        compare3: str | None = None,
    ) -> None:
        compare_names = [n for n in [compare1, compare2, compare3] if n]
        await self._send_chart_embed(interaction, "youtube", name, metric, range_, mode, aggregation, compare_names or None)

    @youtube_chart.autocomplete("name")
    async def _youtube_chart_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current, "youtube")

    @youtube_chart.autocomplete("aggregation")
    async def _youtube_chart_aggregation_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._aggregation_autocomplete(interaction, current, "youtube")

    @youtube_chart.autocomplete("compare1")
    async def _youtube_chart_compare1_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        name = getattr(interaction.namespace, "name", "")
        return await self._name_autocomplete(interaction, current, "youtube", {name} if name else None)

    @youtube_chart.autocomplete("compare2")
    async def _youtube_chart_compare2_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        name = getattr(interaction.namespace, "name", "")
        c1 = getattr(interaction.namespace, "compare1", "")
        exclude = {x for x in (name, c1) if x}
        return await self._name_autocomplete(interaction, current, "youtube", exclude if exclude else None)

    @youtube_chart.autocomplete("compare3")
    async def _youtube_chart_compare3_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        name = getattr(interaction.namespace, "name", "")
        c1 = getattr(interaction.namespace, "compare1", "")
        c2 = getattr(interaction.namespace, "compare2", "")
        exclude = {x for x in (name, c1, c2) if x}
        return await self._name_autocomplete(interaction, current, "youtube", exclude if exclude else None)

    # ------------------------------------------------------------------
    # Spotify chart
    # ------------------------------------------------------------------

    @spotify.command(name="chart", description="Chart a metric for a Spotify item.")
    @app_commands.describe(
        name="The track or album name.",
        metric="Which metric to chart.",
        range_="Time range to show.",
        mode="Total values or per-tick delta.",
        aggregation="Bucket size for resolution.",
        compare1="A second item to compare.",
        compare2="A third item to compare.",
        compare3="A fourth item to compare.",
    )
    @app_commands.choices(metric=SPOTIFY_TYPE_CHOICES, range_=RANGE_CHOICES, mode=MODE_CHOICES)
    @app_commands.rename(metric="type", range_="range", aggregation="resolution")
    @requires_stats_access()
    async def spotify_chart(
        self,
        interaction: discord.Interaction,
        name: str,
        metric: str = "popularity",
        range_: str = "24h",
        mode: str = "delta",
        aggregation: str | None = "hourly",
        compare1: str | None = None,
        compare2: str | None = None,
        compare3: str | None = None,
    ) -> None:
        compare_names = [n for n in [compare1, compare2, compare3] if n]
        await self._send_chart_embed(interaction, "spotify", name, metric, range_, mode, aggregation, compare_names or None)

    @spotify_chart.autocomplete("name")
    async def _spotify_chart_name_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._name_autocomplete(interaction, current, "spotify")

    @spotify_chart.autocomplete("aggregation")
    async def _spotify_chart_aggregation_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._aggregation_autocomplete(interaction, current, "spotify")

    @spotify_chart.autocomplete("compare1")
    async def _spotify_chart_compare1_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        name = getattr(interaction.namespace, "name", "")
        return await self._name_autocomplete(interaction, current, "spotify", {name} if name else None)

    @spotify_chart.autocomplete("compare2")
    async def _spotify_chart_compare2_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        name = getattr(interaction.namespace, "name", "")
        c1 = getattr(interaction.namespace, "compare1", "")
        exclude = {x for x in (name, c1) if x}
        return await self._name_autocomplete(interaction, current, "spotify", exclude if exclude else None)

    @spotify_chart.autocomplete("compare3")
    async def _spotify_chart_compare3_ac(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        name = getattr(interaction.namespace, "name", "")
        c1 = getattr(interaction.namespace, "compare1", "")
        c2 = getattr(interaction.namespace, "compare2", "")
        exclude = {x for x in (name, c1, c2) if x}
        return await self._name_autocomplete(interaction, current, "spotify", exclude if exclude else None)


async def setup(bot: StankBot) -> None:
    await bot.add_cog(StatsCommands(bot))
