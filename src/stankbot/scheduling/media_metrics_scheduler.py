"""Media metrics scheduler — per-guild per-provider interval-based metric refreshes.

One IntervalTrigger job per (guild, provider_type). Each job reads its own
provider-specific interval from guild settings and refreshes only items of
that type. Jobs are aligned to clock boundaries.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from stankbot.db.models import Guild
from stankbot.services.media_providers.registry import MediaProviderRegistry
from stankbot.services.media_service import MediaService
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.web.routes.media_api import cleanup_chart_cache

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)

_INTERVAL_KEYS: dict[str, str] = {
    "youtube": Keys.MEDIA_YOUTUBE_UPDATE_INTERVAL_MINUTES,
    "spotify": Keys.MEDIA_SPOTIFY_UPDATE_INTERVAL_MINUTES,
}


def _media_provider_job_id(guild_id: int, media_type: str) -> str:
    return f"g{guild_id}:media-metrics:{media_type}"


def _align_start(interval_minutes: int) -> datetime:
    """Compute the next clock-aligned boundary after now."""
    now = datetime.now(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_since_midnight = now.hour * 60 + now.minute + now.second / 60 + now.microsecond / 60_000_000
    current_boundary = int(minutes_since_midnight // interval_minutes) * interval_minutes
    next_boundary = current_boundary + interval_minutes
    return midnight + timedelta(minutes=next_boundary)


class MediaMetricsScheduler:
    """Periodically fetches metrics per-guild, per-provider."""

    def __init__(self, bot: StankBot, registry: MediaProviderRegistry) -> None:
        self.bot = bot
        self.registry = registry
        self.scheduler = AsyncIOScheduler(timezone=UTC)

    async def start(self) -> None:
        await self.sync_all_guilds()
        self.scheduler.add_job(
            self._cleanup_chart_cache,
            IntervalTrigger(minutes=10, timezone=UTC),
            id="media:cleanup-chart-cache",
            replace_existing=True,
            misfire_grace_time=60,
        )
        if not self.scheduler.running:
            self.scheduler.start()
        log.info("MediaMetricsScheduler started")

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def sync_all_guilds(self) -> None:
        # Remove pre-v2.44 single-job-per-guild entries (no provider suffix).
        stale_pattern = re.compile(r'^g\d+:media-metrics$')
        for job in self.scheduler.get_jobs():
            if stale_pattern.match(job.id):
                job.remove()
                log.info("MediaMetrics: removed stale job %s", job.id)

        async with self.bot.db() as session:
            guilds = list((await session.execute(select(Guild.id))).scalars())
        for gid in guilds:
            await self.sync_guild(gid)

    async def sync_guild(self, guild_id: int, media_type: str | None = None) -> None:
        """Schedule per-provider jobs for a guild.

        When media_type is None (initial sync), creates a job for every
        enabled provider. When called with a specific type (settings change),
        only recreates that provider's job.
        """
        for provider in self.registry.enabled():
            if media_type is not None and provider.media_type != media_type:
                continue
            await self._sync_provider(guild_id, provider.media_type)

    async def _sync_provider(self, guild_id: int, provider_type: str) -> None:
        job_id = _media_provider_job_id(guild_id, provider_type)
        job = self.scheduler.get_job(job_id)
        if job is not None:
            job.remove()

        key = _INTERVAL_KEYS.get(provider_type)
        if key is None:
            log.warning("MediaMetrics: no interval key for provider %r — defaulting to 60 min", provider_type)
            key = Keys.MEDIA_YOUTUBE_UPDATE_INTERVAL_MINUTES
        async with self.bot.db() as session:
            settings = SettingsService(session)
            interval = await settings.get(guild_id, key, 60)
        interval = max(1, int(interval))
        start_date = _align_start(interval)

        self.scheduler.add_job(
            self._refresh_provider,
            IntervalTrigger(minutes=interval, timezone=UTC, start_date=start_date),
            args=[guild_id, provider_type],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=min(interval * 30, 300),
        )
        log.info("MediaMetrics: guild=%d provider=%s interval=%dm start=%s", guild_id, provider_type, interval, start_date.isoformat())

    async def _refresh_provider(self, guild_id: int, provider_type: str) -> None:
        now = datetime.now(tz=UTC)
        log.info("MediaMetrics: refreshing guild=%d provider=%s", guild_id, provider_type)
        async with self.bot.db() as session:
            svc = MediaService(session=session, registry=self.registry)
            result = await svc.refresh_all(guild_id, media_type=provider_type)
        elapsed = (datetime.now(tz=UTC) - now).total_seconds()
        log.info(
            "MediaMetrics: guild=%d provider=%s refreshed=%d failed=%d in %.1fs",
            guild_id, provider_type, result.refreshed, result.failed, elapsed,
        )

    async def _cleanup_chart_cache(self) -> None:
        deleted = cleanup_chart_cache()
        if deleted:
            log.info("Chart cache cleanup: deleted %d files", deleted)
