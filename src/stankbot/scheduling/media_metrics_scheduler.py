"""Media metrics scheduler — per-guild interval-based metric refreshes.

Follows SessionScheduler pattern: owns an APScheduler instance, registers
one IntervalTrigger job per guild, and syncs when settings change.

Jobs are aligned to clock boundaries: a 60-min interval fires at XX:00,
a 10-min interval fires at XX:00, XX:10, XX:20, etc.
"""

from __future__ import annotations

import logging
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


def _media_guild_job_id(guild_id: int) -> str:
    return f"g{guild_id}:media-metrics"


def _align_start(interval_minutes: int) -> datetime:
    """Compute the next clock-aligned boundary after now.

    e.g., interval=60, now=15:37 → 16:00
          interval=10, now=15:07 → 15:10
          interval=15, now=15:00:01 → 15:15
    """
    now = datetime.now(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_since_midnight = now.hour * 60 + now.minute + now.second / 60 + now.microsecond / 60_000_000
    current_boundary = int(minutes_since_midnight // interval_minutes) * interval_minutes
    next_boundary = current_boundary + interval_minutes
    return midnight + timedelta(minutes=next_boundary)


class MediaMetricsScheduler:
    """Periodically fetches metrics for all media items in each guild."""

    def __init__(self, bot: StankBot, registry: MediaProviderRegistry) -> None:
        self.bot = bot
        self.registry = registry
        self.scheduler = AsyncIOScheduler(timezone=UTC)

    async def start(self) -> None:
        await self.sync_all_guilds()
        # Global chart image cache cleanup every 10 minutes
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
        async with self.bot.db() as session:
            guilds = list((await session.execute(select(Guild.id))).scalars())
        for gid in guilds:
            await self.sync_guild(gid)

    async def sync_guild(self, guild_id: int) -> None:
        self._clear_guild_jobs(guild_id)
        async with self.bot.db() as session:
            settings = SettingsService(session)
            interval = await settings.get(
                guild_id, Keys.MEDIA_METRICS_UPDATE_INTERVAL_MINUTES, 60
            )
        interval = max(5, int(interval))
        start_date = _align_start(interval)

        self.scheduler.add_job(
            self._refresh_guild,
            IntervalTrigger(minutes=interval, timezone=UTC, start_date=start_date),
            args=[guild_id],
            id=_media_guild_job_id(guild_id),
            replace_existing=True,
            misfire_grace_time=min(interval * 30, 300),
        )
        log.info("MediaMetrics: guild=%d interval=%dm start=%s", guild_id, interval, start_date.isoformat())

    def _clear_guild_jobs(self, guild_id: int) -> None:
        job_id = _media_guild_job_id(guild_id)
        job = self.scheduler.get_job(job_id)
        if job is not None:
            job.remove()

    async def _refresh_guild(self, guild_id: int) -> None:
        now = datetime.now(tz=UTC)
        log.info("MediaMetrics: refreshing guild=%d", guild_id)
        async with self.bot.db() as session:
            svc = MediaService(session=session, registry=self.registry)
            result = await svc.refresh_all(guild_id)
        elapsed = (datetime.now(tz=UTC) - now).total_seconds()
        log.info(
            "MediaMetrics: guild=%d refreshed=%d failed=%d in %.1fs",
            guild_id,
            result.refreshed,
            result.failed,
            elapsed,
        )

    async def _cleanup_chart_cache(self) -> None:
        deleted = cleanup_chart_cache()
        if deleted:
            log.info("Chart cache cleanup: deleted %d files", deleted)
