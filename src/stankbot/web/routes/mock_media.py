"""Mock media API — only mounted when ENV=dev-mock.

Allows E2E tests to inject media items and mock metrics directly into the DB
without needing real YouTube/Spotify API keys.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.engine import session_scope
from stankbot.db.models import MediaItem, MetricCache, MetricSnapshot
from stankbot.db.repositories import media as media_repo
from stankbot.web.transport import MsgPackResponse, msgpack_body

router = APIRouter(prefix="/api/mock", tags=["mock-media"])
log = logging.getLogger(__name__)


def _dev_only(request: Request) -> None:
    config = request.app.state.config
    if config.env != "dev-mock":
        raise HTTPException(status_code=403, detail="Mock endpoints only available in dev-mock mode")


class MockClearMediaPayload(BaseModel):
    guild_id: int = 123456789


@router.post("/clear-media")
async def mock_clear_media(
    request: Request,
    payload: MockClearMediaPayload = msgpack_body(MockClearMediaPayload),  # type: ignore[assignment]
) -> MsgPackResponse:
    _dev_only(request)

    async with session_scope(request.app.state.session_factory) as session:
        items = (await session.execute(
            select(MediaItem.id).where(MediaItem.guild_id == payload.guild_id)
        )).scalars().all()

        if items:
            await session.execute(
                delete(MetricSnapshot).where(
                    MetricSnapshot.media_item_id.in_(items)
                )
            )
            await session.execute(
                delete(MetricCache).where(
                    MetricCache.media_item_id.in_(items)
                )
            )
            await session.execute(
                delete(MediaItem).where(MediaItem.guild_id == payload.guild_id)
            )

    return MsgPackResponse({"success": True}, request)


class MockMediaPayload(BaseModel):
    guild_id: int
    media_type: str = "youtube"
    external_id: str | None = None
    slug: str | None = None


@router.post("/media")
async def mock_add_media(
    request: Request,
    payload: MockMediaPayload = msgpack_body(MockMediaPayload),  # type: ignore[assignment]
) -> MsgPackResponse:
    _dev_only(request)

    guild_id = payload.guild_id
    media_type = payload.media_type
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    external_id = (
        payload.external_id
        or f"mock_{media_type}_{guild_id}_{stamp}"
    )
    base_slug = payload.slug or f"mock-{media_type}-{stamp[-12:]}"

    async with session_scope(request.app.state.session_factory) as session:
        # Handle slug collisions by appending a counter
        slug = base_slug
        attempt = 0
        max_attempts = 10
        while attempt < max_attempts:
            try:
                item = await media_repo.add(
                    session,
                    guild_id=guild_id,
                    media_type=media_type,
                    external_id=f"{external_id}_{attempt}" if attempt > 0 else external_id,
                    title=f"Mock {media_type.capitalize()} Item — {slug}",
                    channel_name="Mock Channel",
                    thumbnail_url=None,
                    published_at=datetime.now(tz=timezone.utc),
                    duration_seconds=180,
                    added_by=111111111,
                    slug=slug,
                )
                break
            except Exception:
                await session.rollback()
                attempt += 1
                slug = f"{base_slug}-{attempt}"
        else:
            raise HTTPException(status_code=500, detail="Failed to insert mock media after retries")

        # Add fake metrics
        now = datetime.now(tz=timezone.utc)
        metric_values = {"view_count": 10000, "like_count": 500, "comment_count": 50}
        if media_type == "spotify":
            metric_values = {"popularity": 75}

        for key, val in metric_values.items():
            await media_repo.upsert_metric_cache(session, item.id, key, val, now)
            await media_repo.insert_metric_snapshot(session, item.id, key, val, now)

        # Add a second snapshot for history
        older = datetime(2026, 4, 15, tzinfo=timezone.utc)
        for key, val in metric_values.items():
            await media_repo.insert_metric_snapshot(
                session, item.id, key, val // 2, older
            )

        item.metrics_last_fetched_at = now

    return MsgPackResponse(
        {"success": True, "id": item.id, "slug": slug}, request, status_code=201
    )
