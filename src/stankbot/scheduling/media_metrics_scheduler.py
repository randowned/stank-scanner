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
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Guild
from stankbot.db.repositories import media as media_repo
from stankbot.services.announcement_service import broadcast_media_milestone
from stankbot.services.embed_builders import build_media_milestone_embed
from stankbot.services.media_providers.registry import MediaProviderRegistry
from stankbot.services.media_service import MediaService, MilestoneInfo
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.utils.time_utils import utc_isoformat
from stankbot.web.routes.media_api import cleanup_chart_cache
from stankbot.web.ws import broadcast_media_milestone as ws_broadcast_milestone
from stankbot.web.ws import broadcast_media_snapshot as ws_broadcast_snapshot

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

        Respects ``MEDIA_PROVIDERS_ENABLED``: disabled providers get their
        jobs removed and no new job is created.
        """
        async with self.bot.db() as session:
            settings = SettingsService(session)
            enabled = await settings.get(guild_id, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"])
        for provider in self.registry.enabled():
            if media_type is not None and provider.media_type != media_type:
                continue
            if provider.media_type not in enabled:
                job_id = _media_provider_job_id(guild_id, provider.media_type)
                job = self.scheduler.get_job(job_id)
                if job is not None:
                    job.remove()
                    log.info("MediaMetrics: guild=%d provider=%s disabled — removed job", guild_id, provider.media_type)
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
        async with self.bot.db() as session:
            provider = self.registry.get(provider_type)
            if provider is not None and not await provider.can_fetch_metrics(session, guild_id):
                log.debug("MediaMetrics: skipping guild=%d provider=%s (cannot fetch metrics)", guild_id, provider_type)
                return
            settings = SettingsService(session)
            enabled = await settings.get(guild_id, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"])
            if provider_type not in enabled:
                log.debug("MediaMetrics: skipping guild=%d provider=%s (disabled by guild setting)", guild_id, provider_type)
                return
            svc = MediaService(session=session, registry=self.registry)

            async def _on_snapshot(*, media_item_id: int, metric_key: str,
                                   value: int, fetched_at: datetime) -> None:
                await ws_broadcast_snapshot(
                    guild_id,
                    media_item_id=media_item_id,
                    metric_key=metric_key,
                    value=value,
                    fetched_at=utc_isoformat(fetched_at),
                )

            result = await svc.refresh_all(guild_id, media_type=provider_type,
                                             on_snapshot=_on_snapshot)

            # Milestone announcements
            for minfo in result.milestones:
                await self._announce_milestone(session, guild_id, minfo)

        elapsed = (datetime.now(tz=UTC) - now).total_seconds()
        log.info(
            "MediaMetrics: guild=%d provider=%s refreshed=%d failed=%d milestones=%d in %.1fs",
            guild_id, provider_type, result.refreshed, result.failed,
            len(result.milestones), elapsed,
        )

    async def _announce_milestone(
        self,
        session: AsyncSession,
        guild_id: int,
        minfo: MilestoneInfo,
    ) -> None:
        settings = SettingsService(session)
        milestones_enabled = await settings.get(guild_id, Keys.MEDIA_ANNOUNCE_MILESTONES, True)
        if not milestones_enabled:
            return
        media_channel = await settings.get(guild_id, Keys.MEDIA_ANNOUNCE_CHANNEL_ID, None)

        # Build compact other-metrics string
        other_parts: list[str] = []
        cache = await media_repo.get_metric_cache(session, minfo.media_item_id)
        provider = self.registry.get(minfo.media_type)
        if provider:
            for mdef in provider.metrics:
                if mdef.key == minfo.metric_key:
                    continue
                mv = cache.get(mdef.key, {})
                if isinstance(mv, dict) and int(mv.get("value", 0)):
                    cv = int(mv["value"])
                    if cv >= 1_000_000_000:
                        fm = f"{cv / 1_000_000_000:.1f}B".replace(".0B", "B")
                    elif cv >= 1_000_000:
                        fm = f"{cv / 1_000_000:.1f}M".replace(".0M", "M")
                    elif cv >= 1_000:
                        fm = f"{cv / 1_000:.1f}K".replace(".0K", "K")
                    else:
                        fm = str(cv)
                    other_parts.append(f"{mdef.icon} {fm}")
        other_metrics = "  \u00b7  ".join(other_parts) if other_parts else "—"

        base_url = self.bot.config.oauth_redirect_uri.rsplit("/", 2)[0]
        chart_url = (
            f"{base_url}/api/media/{minfo.media_item_id}/chart"
            f"?metric={minfo.metric_key}&hours=12&mode=total&aggregation=30min"
        )

        embed = await build_media_milestone_embed(
            info=minfo,
            other_metrics=other_metrics,
            chart_url=chart_url,
            guild_id=guild_id,
            session=session,
            base_url=base_url,
        )
        await broadcast_media_milestone(
            session,
            self.bot,
            guild_id=guild_id,
            embed=embed,
            media_announce_channel_id=media_channel,
            milestones_enabled=True,
        )
        await ws_broadcast_milestone(
            guild_id,
            media_item_id=minfo.media_item_id,
            media_type=minfo.media_type,
            metric_key=minfo.metric_key,
            milestone_value=minfo.milestone_value,
            new_value=minfo.new_value,
            title=minfo.title,
            channel_name=minfo.channel_name,
            thumbnail_url=minfo.thumbnail_url,
            name=minfo.name,
            external_id=minfo.external_id,
        )
        log.info(
            "MediaMilestone: guild=%d item=%d metric=%s milestone=%s announced",
            guild_id, minfo.media_item_id, minfo.metric_key,
            f"{minfo.milestone_value:,}",
        )

    async def _cleanup_chart_cache(self) -> None:
        deleted = cleanup_chart_cache()
        if deleted:
            log.info("Chart cache cleanup: deleted %d files", deleted)
