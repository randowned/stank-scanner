"""Unit tests for MediaMetricsScheduler — enabled-provider gating in
_refresh_provider and sync_guild."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Guild
from stankbot.scheduling.media_metrics_scheduler import (
    MediaMetricsScheduler,
    _media_provider_job_id,
)
from stankbot.services.media_providers.registry import MediaProviderRegistry
from stankbot.services.media_providers.spotify import SpotifyProvider
from stankbot.services.media_providers.youtube import YouTubeProvider
from stankbot.services.settings_service import Keys, SettingsService


class _FakeBot:
    """Minimal bot stub that yields *session* from its db() context manager."""

    def __init__(self, session: AsyncSession) -> None:
        self.config = Mock()
        self._session = session

    @asynccontextmanager
    async def db(self) -> AsyncIterator[AsyncSession]:
        yield self._session


# ── _refresh_provider tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_provider_skips_disabled(session: Any) -> None:
    session.add(Guild(id=2))
    settings_svc = SettingsService(session)
    await settings_svc.set(2, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube"])
    await session.flush()

    registry = MediaProviderRegistry()
    registry.register(YouTubeProvider(api_key="fake-key"))
    registry.register(SpotifyProvider(client_id="fake-id", client_secret="fake-secret"))

    bot = _FakeBot(session)
    scheduler = MediaMetricsScheduler(bot, registry)  # type: ignore[arg-type]
    scheduler.scheduler = AsyncIOScheduler()

    with patch("stankbot.services.media_service.MediaService.refresh_all", new_callable=AsyncMock) as mock_refresh:
        await scheduler._refresh_provider(2, "spotify")

    mock_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_provider_proceeds_when_enabled(session: Any) -> None:
    session.add(Guild(id=3))
    settings_svc = SettingsService(session)
    await settings_svc.set(3, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"])
    await session.flush()

    registry = MediaProviderRegistry()
    registry.register(YouTubeProvider(api_key="fake-key"))
    registry.register(SpotifyProvider(client_id="fake-id", client_secret="fake-secret"))

    bot = _FakeBot(session)
    scheduler = MediaMetricsScheduler(bot, registry)  # type: ignore[arg-type]
    scheduler.scheduler = AsyncIOScheduler()

    with patch("stankbot.services.media_service.MediaService.refresh_all", new_callable=AsyncMock) as mock_refresh:
        await scheduler._refresh_provider(3, "spotify")

    mock_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_provider_uses_default_when_no_setting_row(session: Any) -> None:
    session.add(Guild(id=4))
    await session.flush()

    registry = MediaProviderRegistry()
    registry.register(YouTubeProvider(api_key="fake-key"))
    registry.register(SpotifyProvider(client_id="fake-id", client_secret="fake-secret"))

    bot = _FakeBot(session)
    scheduler = MediaMetricsScheduler(bot, registry)  # type: ignore[arg-type]
    scheduler.scheduler = AsyncIOScheduler()

    with patch("stankbot.services.media_service.MediaService.refresh_all", new_callable=AsyncMock) as mock_refresh:
        await scheduler._refresh_provider(4, "spotify")

    mock_refresh.assert_called_once()


# ── sync_guild tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_guild_creates_jobs_for_enabled_only(session: Any) -> None:
    session.add(Guild(id=5))
    settings_svc = SettingsService(session)
    await settings_svc.set(5, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube"])
    await session.flush()

    registry = MediaProviderRegistry()
    registry.register(YouTubeProvider(api_key="fake-key"))
    registry.register(SpotifyProvider(client_id="fake-id", client_secret="fake-secret"))

    bot = _FakeBot(session)
    scheduler = MediaMetricsScheduler(bot, registry)  # type: ignore[arg-type]
    scheduler.scheduler = AsyncIOScheduler()

    sync_calls: list[str] = []

    async def _fake_sync_provider(guild_id: int, provider_type: str) -> None:
        sync_calls.append(provider_type)

    scheduler._sync_provider = _fake_sync_provider  # type: ignore[method-assign]

    await scheduler.sync_guild(5)

    assert sync_calls == ["youtube"]


@pytest.mark.asyncio
async def test_sync_guild_removes_jobs_for_disabled(session: Any) -> None:
    session.add(Guild(id=6))
    settings_svc = SettingsService(session)
    await settings_svc.set(6, Keys.MEDIA_PROVIDERS_ENABLED, [])
    await session.flush()

    registry = MediaProviderRegistry()
    registry.register(YouTubeProvider(api_key="fake-key"))
    registry.register(SpotifyProvider(client_id="fake-id", client_secret="fake-secret"))

    bot = _FakeBot(session)
    scheduler = MediaMetricsScheduler(bot, registry)  # type: ignore[arg-type]
    scheduler.scheduler = AsyncIOScheduler()

    # Pre-register jobs for both providers so we can assert removal
    from datetime import UTC

    from apscheduler.triggers.interval import IntervalTrigger

    yt_job_id = _media_provider_job_id(6, "youtube")
    sp_job_id = _media_provider_job_id(6, "spotify")
    scheduler.scheduler.add_job(
        AsyncMock(), IntervalTrigger(minutes=60, timezone=UTC),
        id=yt_job_id, args=[6, "youtube"],
    )
    scheduler.scheduler.add_job(
        AsyncMock(), IntervalTrigger(minutes=60, timezone=UTC),
        id=sp_job_id, args=[6, "spotify"],
    )

    assert scheduler.scheduler.get_job(yt_job_id) is not None
    assert scheduler.scheduler.get_job(sp_job_id) is not None

    await scheduler.sync_guild(6)

    assert scheduler.scheduler.get_job(yt_job_id) is None
    assert scheduler.scheduler.get_job(sp_job_id) is None
