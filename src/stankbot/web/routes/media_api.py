"""User-facing media API — list, detail, history, comparison.

All routes require guild membership. Data comes from the MediaService
which delegates to the provider registry stored on app.state.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.repositories import media as media_repo
from stankbot.services.chart_renderer import render_media_chart
from stankbot.services.media_service import MediaService
from stankbot.web.tools import get_active_guild_id, get_db, require_guild_member
from stankbot.web.transport import MsgPackResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])


async def _media_service(
    request: Request,
    session: AsyncSession,
) -> MediaService:
    registry = request.app.state.media_registry
    return MediaService(session=session, registry=registry)


@router.get("")
async def list_media(
    request: Request,
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    media_type: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    svc = await _media_service(request, session)
    items = await svc.list_media(guild_id, media_type)
    return MsgPackResponse({"items": items}, request)


@router.get("/compare")
async def compare_media(
    request: Request,
    ids: str = Query(None),
    slugs: str = Query(None),
    metric: str = Query("view_count"),
    days: int = Query(30, ge=1, le=365),
    align: str = Query("calendar"),
    delta: bool = Query(True),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    media_ids: list[int] = []
    if ids:
        try:
            media_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="ids must be comma-separated integers") from exc
    elif slugs:
        slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
        if not slug_list:
            raise HTTPException(status_code=400, detail="slugs must be comma-separated non-empty strings")
        items_by_slug = await media_repo.get_by_slugs(session, guild_id, slug_list)
        # Preserve slugs order
        media_ids = [items_by_slug[s].id for s in slug_list if s in items_by_slug]
    else:
        raise HTTPException(status_code=400, detail="either ids or slugs parameter is required")
    if len(media_ids) < 2:
        raise HTTPException(status_code=400, detail="at least 2 ids required for comparison")
    if len(media_ids) > 10:
        media_ids = media_ids[:10]

    svc = await _media_service(request, session)
    data = await svc.get_comparison_data(
        media_ids, metric, window_days=days, align_release=(align == "release"), delta=delta
    )
    return MsgPackResponse(data, request)


@router.get("/providers")
async def list_providers(
    request: Request,
    _user: dict[str, Any] = Depends(require_guild_member),
) -> MsgPackResponse:
    registry = request.app.state.media_registry
    providers = [
        {
            "type": d.type,
            "label": d.label,
            "icon": d.icon,
            "metrics": [
                {"key": m.key, "label": m.label, "format": m.format, "icon": m.icon}
                for m in d.metrics
            ],
        }
        for d in registry.all_defs()
    ]
    return MsgPackResponse({"providers": providers}, request)


@router.get("/{media_id}")
async def get_media_detail(
    request: Request,
    media_id: int,
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    svc = await _media_service(request, session)
    item = await svc.get_media_item(media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    return MsgPackResponse(item, request)


@router.get("/{media_id}/history")
async def get_media_history(
    request: Request,
    media_id: int,
    metric: str = Query("view_count"),
    days: int = Query(30, ge=1, le=365),
    hours: int | None = Query(None, ge=1, le=48),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    svc = await _media_service(request, session)
    history = await svc.get_metrics_history(
        media_id, metric, window_days=days, window_hours=hours
    )
    payload: dict[str, Any] = {"metric": metric, "days": days, "history": history}
    if hours is not None:
        payload["hours"] = hours
    return MsgPackResponse(payload, request)


# ---------------------------------------------------------------------------
# Public chart image endpoint (no auth — embedded in Discord)
# ---------------------------------------------------------------------------


CHART_CACHE_DIR = Path(
    os.environ.get(
        "CHART_CACHE_DIR",
        str(Path(__file__).parent.parent.parent.parent.parent / "data" / "media" / "chart"),
    )
)


@router.get("/{media_id}/chart", include_in_schema=False)
async def get_media_chart(
    request: Request,
    media_id: int,
    metric: str = Query("view_count"),
    days: int | None = Query(None, ge=0, le=365),
    hours: int | None = Query(None, ge=1, le=8760),
    date: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    item = await media_repo.get(session, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")

    registry = request.app.state.media_registry
    provider = registry.get(item.media_type)
    metric_label = metric
    if provider:
        for m in provider.metrics:
            if m.key == metric:
                metric_label = m.label
                break

    # Resolve reference date
    if date:
        try:
            reference_date = datetime.fromisoformat(date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date}") from exc
    else:
        reference_date = datetime.now(UTC)

    # Resolve time window
    window_hours: int | None = None
    window_days: int | None = None
    if hours is not None:
        window_hours = hours
    elif days is not None and days > 0:
        window_days = days
    else:
        window_days = 7  # default 1 week

    # Fetch all snapshots in range
    if window_hours is not None:
        since = reference_date - timedelta(hours=window_hours)
    elif window_days is not None:
        since = reference_date - timedelta(days=window_days)
    else:
        since = None  # "all"

    snaps_by_id = await media_repo.get_comparison_snapshots(
        session, [media_id], metric, since
    )
    snaps = snaps_by_id.get(media_id, [])
    # Filter snapshots at or before reference_date
    snaps = [s for s in snaps if s.fetched_at <= reference_date]

    # Determine cache key from the latest snapshot timestamp
    if snaps:
        latest_snap = snaps[-1]
        cache_ts = int(latest_snap.fetched_at.timestamp())
    else:
        cache_ts = int(reference_date.timestamp())

    cache_dir = CHART_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{media_id}_{cache_ts}.png"

    if cache_path.exists():
        return FileResponse(
            cache_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Compute actual duration for chart title context
    if snaps:
        duration_hours = (max(s.fetched_at for s in snaps) - min(s.fetched_at for s in snaps)).total_seconds() / 3600
    else:
        duration_hours = 0.0

    buf = render_media_chart(
        snapshots=snaps,
        title=item.title,
        metric_label=metric_label,
        duration_hours=duration_hours,
    )
    cache_path.write_bytes(buf)

    return FileResponse(
        cache_path, media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
