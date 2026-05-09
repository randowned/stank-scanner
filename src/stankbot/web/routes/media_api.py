"""User-facing media API — list, detail, history, comparison.

All routes require guild membership. Data comes from the MediaService
which delegates to the provider registry stored on app.state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.repositories import media as media_repo
from stankbot.services.chart_renderer import render_compare_chart, render_media_chart
from stankbot.services.media_service import MediaService, _aggregate_snapshots, _floor_to_bucket
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.web.tools import get_active_guild_id, get_db, require_guild_member
from stankbot.web.transport import MsgPackResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])


async def _get_enabled_providers(
    session: AsyncSession,
    guild_id: int,
) -> list[str]:
    return await SettingsService(session).get(
        guild_id, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"]
    )




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
    enabled = await _get_enabled_providers(session, guild_id)
    items = [i for i in items if i["media_type"] in enabled]
    return MsgPackResponse({"items": items}, request)




_PROVIDER_INTERVAL_KEYS: dict[str, str] = {
    "youtube": Keys.MEDIA_YOUTUBE_UPDATE_INTERVAL_MINUTES,
    "spotify": Keys.MEDIA_SPOTIFY_UPDATE_INTERVAL_MINUTES,
}


@router.get("/providers")
async def list_providers(
    request: Request,
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    registry = request.app.state.media_registry
    settings = SettingsService(session)
    enabled = await _get_enabled_providers(session, guild_id)
    providers = []
    for d in registry.all_defs():
        if enabled is not None and d.type not in enabled:
            continue
        interval_key = _PROVIDER_INTERVAL_KEYS.get(d.type)
        interval_minutes: int = (
            await settings.get(guild_id, interval_key, 60) if interval_key else 60
        )
        providers.append({
            "type": d.type,
            "label": d.label,
            "icon": d.icon,
            "metrics": [
                {"key": m.key, "label": m.label, "format": m.format, "icon": m.icon}
                for m in d.metrics
            ],
            "interval_minutes": interval_minutes,
        })
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
    if item["media_type"] not in await _get_enabled_providers(session, guild_id):
        raise HTTPException(status_code=404, detail="Media item not found")
    return MsgPackResponse(item, request)


@router.get("/{media_id}/history")
async def get_media_history(
    request: Request,
    media_id: int,
    metric: str = Query("view_count"),
    days: int = Query(30, ge=1, le=365),
    hours: int | None = Query(None, ge=1, le=48),
    aggregation: str | None = Query(None, pattern=r"^(5min|15min|30min|hourly|daily|weekly|monthly)$"),
    mode: str = Query("total", pattern=r"^(total|delta)$"),
    compare_ids: str | None = Query(None),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    item = await media_repo.get(session, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    if item.media_type not in await _get_enabled_providers(session, guild_id):
        raise HTTPException(status_code=404, detail="Media item not found")
    svc = await _media_service(request, session)
    history = await svc.get_metrics_history(
        media_id, metric, window_days=days, window_hours=hours,
        aggregation=aggregation, mode=mode,
    )
    payload: dict[str, Any] = {"metric": metric, "days": days, "history": history}
    if hours is not None:
        payload["hours"] = hours
    if aggregation:
        payload["aggregation"] = aggregation
    if mode != "total":
        payload["mode"] = mode

    if compare_ids:
        try:
            extra_ids = [int(x.strip()) for x in compare_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="compare_ids must be comma-separated integers") from exc
        all_ids = [media_id] + [eid for eid in extra_ids if eid != media_id]
        if len(all_ids) >= 2:
            compare = await svc.get_comparison_data(
                all_ids, metric,
                window_days=days, window_hours=hours,
                align_release=False, delta=(mode == "delta"),
                aggregation=aggregation,
            )
            payload["compare"] = compare

    return MsgPackResponse(payload, request)


# ---------------------------------------------------------------------------
# Public chart image endpoint (no auth — embedded in Discord)
# ---------------------------------------------------------------------------


CHART_CACHE_DIR = Path(
    os.environ.get("CHART_CACHE_DIR", "/data/media/chart")
)


@dataclass(slots=True)
class _SnapshotStub:
    value: int
    fetched_at: datetime


@router.get("/{media_id}/chart", include_in_schema=False)
async def get_media_chart(
    request: Request,
    media_id: int,
    metric: str = Query("view_count"),
    days: int | None = Query(None, ge=0, le=365),
    hours: int | None = Query(None, ge=1, le=8760),
    date: str | None = Query(None),
    mode: str = Query("total"),
    aggregation: str | None = Query(None, pattern=r"^(5min|15min|30min|hourly|daily|weekly|monthly)$"),
    compare_ids: str | None = Query(None),
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
            normalized = date.replace(" ", "+").replace("Z", "+00:00")
            reference_date = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date}") from exc
    else:
        reference_date = datetime.now(UTC)

    render_mode = mode if mode in ("total", "delta") else "total"
    svc = await _media_service(request, session)

    # Determine cache params
    window_hours: int | None = hours
    window_days: int | None = days if days is not None and days > 0 else None
    if window_hours is None and window_days is None:
        window_days = 7

    if compare_ids:
        try:
            extra_ids = [int(x.strip()) for x in compare_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="compare_ids must be comma-separated integers") from exc
        all_ids = [media_id] + [eid for eid in extra_ids if eid != media_id]
        if len(all_ids) >= 2:
            compare = await svc.get_comparison_data(
                all_ids, metric,
                window_days=window_days or 30, window_hours=window_hours,
                align_release=False, delta=(render_mode == "delta"),
                aggregation=aggregation, reference_date=reference_date,
            )
            series = compare.get("series", [])
            if not any(s.get("points") for s in series):
                raise HTTPException(status_code=404, detail="No data available")
        else:
            series = []
    else:
        series = []

    if series:
        # Compare chart
        buf = render_compare_chart(
            series=series, title=metric_label, metric_label=metric_label,
        )
        # Cache key for compare chart
        ids_key = "_".join(str(s.get("media_item_id", "")) for s in series)
        cache_ts = int(reference_date.timestamp())
    else:
        # Single-item chart — use MediaService for DRY data fetching
        history = await svc.get_metrics_history(
            media_id, metric,
            window_days=window_days or 30, window_hours=window_hours,
            aggregation=aggregation, mode=render_mode,
            reference_date=reference_date,
        )
        render_snaps = [
            _SnapshotStub(
                value=int(d["value"]),
                fetched_at=datetime.fromisoformat(d["fetched_at"]),
            )
            for d in history
        ]
        buf = render_media_chart(
            snapshots=render_snaps, title=item.title or "Item",
            metric_label=metric_label, mode=render_mode,
        )
        # Cache key for single chart
        ids_key = str(media_id)
        latest_snap = history[-1] if history else None
        if latest_snap:
            cache_ts = int(datetime.fromisoformat(latest_snap["fetched_at"]).timestamp())
        else:
            cache_ts = int(reference_date.timestamp())

    range_key = f"h{hours}" if hours is not None else f"d{days}" if days is not None else "all"
    agg_key = f"_{aggregation}" if aggregation else ""
    cmp_key = f"_cmp{ids_key}" if series else ""
    cache_dir = CHART_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{media_id}_{metric}_{range_key}{agg_key}{cmp_key}_{cache_ts}_{render_mode}.png"

    if cache_path.exists():
        return FileResponse(
            cache_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    cache_path.write_bytes(buf)
    return FileResponse(
        cache_path, media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


def cleanup_chart_cache(now: datetime | None = None) -> int:
    """Delete cached chart images whose snapshot data is older than 24 hours.

    Returns the number of files deleted.
    """
    if now is None:
        now = datetime.now(UTC)
    cutoff = now.timestamp() - 86400  # 24 hours ago

    cache_dir = CHART_CACHE_DIR
    if not cache_dir.exists():
        return 0

    deleted = 0
    for f in cache_dir.iterdir():
        if not f.is_file() or f.suffix != ".png":
            continue
        try:
            # Filename format: {media_id}_{metric}_{range}_{snapshot_ts}_{mode}.png
            # Find the longest digit-only segment that looks like an epoch timestamp.
            parts = f.stem.split("_")
            for part in reversed(parts):
                if part.isdigit() and len(part) >= 10:
                    if int(part) < cutoff:
                        f.unlink()
                        deleted += 1
                    break
        except (ValueError, OSError):
            continue
    return deleted
