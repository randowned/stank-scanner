"""API-level tests for GET /api/media/{media_id}/history with the optional
compare_ids parameter added in v2.30.0.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Guild, MediaItem, MetricSnapshot
from stankbot.services.media_providers.base import (
    MediaProvider,
    MetricDef,
    MetricResult,
    ResolvedMedia,
)
from stankbot.services.media_providers.registry import MediaProviderRegistry
from stankbot.web.routes.media_api import router as media_router


class _StubProvider(MediaProvider):
    media_type = "youtube"
    label = "YouTube"
    icon = "▶️"
    metrics = [
        MetricDef("view_count", "Views", "number", "👁️"),
        MetricDef("like_count", "Likes", "number", "👍"),
        MetricDef("comment_count", "Comments", "number", "💬"),
    ]

    def is_configured(self) -> bool:
        return True

    async def resolve(self, url_or_id: str) -> ResolvedMedia | None:
        return ResolvedMedia(external_id=url_or_id, title="Test")

    async def fetch_metrics(self, external_ids: list[str]) -> list[MetricResult]:
        return [MetricResult(external_id=eid, values={"view_count": 100}) for eid in external_ids]

    async def health_check(self) -> bool:
        return True


def _build_test_app(db_session: AsyncSession, registry: MediaProviderRegistry) -> FastAPI:
    from stankbot.web.tools import get_active_guild_id, get_db, require_guild_member

    app = FastAPI()

    async def _override_db() -> Any:
        yield db_session

    async def _override_member() -> dict[str, str]:
        return {"id": "1", "username": "testuser"}

    async def _override_guild_id() -> int:
        return 7

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_guild_member] = _override_member
    app.dependency_overrides[get_active_guild_id] = _override_guild_id
    app.state.media_registry = registry
    app.include_router(media_router)
    return app


async def _seed_media_items(session: AsyncSession, guild_id: int = 7) -> tuple[MediaItem, MediaItem, MediaItem]:
    guild = Guild(id=guild_id)
    session.add(guild)
    await session.flush()

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    item1 = MediaItem(guild_id=guild_id, media_type="youtube", external_id="vid1",
                       name="video-1", title="Video 1", added_by=1)
    item2 = MediaItem(guild_id=guild_id, media_type="youtube", external_id="vid2",
                       name="video-2", title="Video 2", added_by=1)
    item3 = MediaItem(guild_id=guild_id, media_type="youtube", external_id="vid3",
                       name="video-3", title="Video 3", added_by=1)
    session.add_all([item1, item2, item3])
    await session.flush()

    for item, base in [(item1, 1000), (item2, 500), (item3, 200)]:
        for i in range(48):
            session.add(MetricSnapshot(
                media_item_id=item.id,
                metric_key="view_count",
                value=base + i * 100,
                fetched_at=now - timedelta(hours=47 - i),
            ))
    await session.flush()
    return item1, item2, item3


@pytest.fixture
def registry() -> MediaProviderRegistry:
    r = MediaProviderRegistry()
    r.register(_StubProvider())
    return r


@pytest.mark.asyncio
async def test_history_no_compare_ids(session: AsyncSession, registry: MediaProviderRegistry) -> None:
    """Without compare_ids, response has no compare key (backward compat)."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=24")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "history" in data
    assert "compare" not in data
    assert data["metric"] == "view_count"
    assert len(data["history"]) > 0


@pytest.mark.asyncio
async def test_history_with_compare_ids_returns_compare_key(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """compare_ids=2 includes compare in response with metric + series."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=24&compare_ids=2")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "history" in data
    assert "compare" in data
    compare = data["compare"]
    assert "metric" in compare
    assert "series" in compare
    assert len(compare["series"]) == 2


@pytest.mark.asyncio
async def test_history_compare_includes_primary_in_series(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """Primary media (id=1) appears in compare.series alongside compare_ids items."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/2/history?metric=view_count&hours=24&compare_ids=1,3")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    series_ids = {s["media_item_id"] for s in data["compare"]["series"]}
    assert series_ids == {1, 2, 3}


@pytest.mark.asyncio
async def test_history_compare_with_aggregation_and_delta(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """aggregation + mode=delta flows through to both history and compare."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/media/1/history?metric=view_count&hours=24"
            "&aggregation=hourly&mode=delta&compare_ids=2"
        )

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["aggregation"] == "hourly"
    assert data["mode"] == "delta"
    assert "compare" in data
    assert len(data["compare"]["series"]) == 2


@pytest.mark.asyncio
async def test_history_compare_with_hours_range(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """hours=12 window applies to both history and comparison."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=12&compare_ids=2")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["hours"] == 12
    assert "compare" in data


@pytest.mark.asyncio
async def test_history_compare_with_days_range(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """days=7 window applies to both history and comparison."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&days=7&compare_ids=2")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["days"] == 7
    assert "compare" in data


@pytest.mark.asyncio
async def test_history_compare_ids_empty_string(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """Empty compare_ids= results in no compare section."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=24&compare_ids=")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "history" in data
    assert "compare" not in data


@pytest.mark.asyncio
async def test_history_compare_ids_invalid(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """Non-integer compare_ids returns 400."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=24&compare_ids=abc")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_history_compare_nonexistent_extra_id_still_returns_history(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """Compare ID that matches no item → primary history is fine, compare
    section contains only the primary item (lenient)."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=24&compare_ids=99999")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "history" in data
    assert len(data["history"]) > 0
    # Compare section is still present (lenient: only primary item has data)
    assert "compare" in data
    assert len(data["compare"]["series"]) == 1
    assert data["compare"]["series"][0]["media_item_id"] == 1


@pytest.mark.asyncio
async def test_history_compare_primary_not_found_404(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """Non-existent primary media_id returns 404, even with compare_ids."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/9999/history?metric=view_count&hours=24&compare_ids=2")

    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_history_compare_primary_duplicate_in_compare_ids_no_dup_in_series(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """When compare_ids includes the primary id, it's deduplicated — only one
    entry per item in the comparison series."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/history?metric=view_count&hours=24&compare_ids=1,2")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "compare" in data
    series_ids = [s["media_item_id"] for s in data["compare"]["series"]]
    assert series_ids == [1, 2]


@pytest.mark.asyncio
async def test_compare_endpoint_removed(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """The old GET /api/media/compare endpoint was removed in favour of
    /api/media/{id}/history?compare_ids=."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/compare?ids=1,2&metric=view_count&hours=24")

    assert resp.status_code in (status.HTTP_404_NOT_FOUND, 422)


@pytest.mark.asyncio
async def test_chart_endpoint_returns_png(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """GET /api/media/{id}/chart returns a PNG image (no auth)."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/1/chart?metric=view_count&hours=24&mode=delta")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers.get("content-type") == "image/png"
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_chart_endpoint_with_compare_ids(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """GET /api/media/{id}/chart with compare_ids returns a compare PNG."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/media/1/chart?metric=view_count&hours=24&mode=delta&compare_ids=2"
        )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers.get("content-type") == "image/png"


@pytest.mark.asyncio
async def test_chart_endpoint_404_for_nonexistent_item(
    session: AsyncSession, registry: MediaProviderRegistry,
) -> None:
    """Chart endpoint returns 404 for non-existent primary item."""
    await _seed_media_items(session)

    app = _build_test_app(session, registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/media/9999/chart?metric=view_count&hours=24")

    assert resp.status_code == status.HTTP_404_NOT_FOUND
