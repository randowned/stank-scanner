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
from stankbot.services.chart_renderer import render_media_chart
from stankbot.services.media_service import MediaService, _aggregate_snapshots
from stankbot.services.permission_service import PermissionService
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


async def _is_admin(
    session: AsyncSession,
    guild_id: int,
    user: dict[str, Any],
    request: Request,
) -> bool:
    config = request.app.state.config
    svc = PermissionService(session, owner_id=config.owner_id)
    return await svc.is_admin(guild_id, int(user["id"]), [], has_manage_guild=False)


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
    if not await _is_admin(session, guild_id, _user, request):
        enabled = await _get_enabled_providers(session, guild_id)
        items = [i for i in items if i["media_type"] in enabled]
    return MsgPackResponse({"items": items}, request)


@router.get("/compare")
async def compare_media(
    request: Request,
    ids: str = Query(None),
    names: str = Query(None),
    metric: str = Query("view_count"),
    days: int = Query(30, ge=1, le=365),
    hours: int | None = Query(None, ge=1, le=48),
    align: str = Query("calendar"),
    delta: bool = Query(True),
    aggregation: str | None = Query(None, pattern=r"^(5min|15min|hourly|daily|weekly|monthly)$"),
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
    elif names:
        name_list = [s.strip() for s in names.split(",") if s.strip()]
        if not name_list:
            raise HTTPException(status_code=400, detail="names must be comma-separated non-empty strings")
        items_by_name = await media_repo.get_by_names(session, guild_id, name_list)
        # Preserve names order
        media_ids = [items_by_name[s].id for s in name_list if s in items_by_name]
    else:
        raise HTTPException(status_code=400, detail="either ids or names parameter is required")
    if len(media_ids) < 2:
        raise HTTPException(status_code=400, detail="at least 2 ids required for comparison")
    if len(media_ids) > 10:
        media_ids = media_ids[:10]

    svc = await _media_service(request, session)
    data = await svc.get_comparison_data(
        media_ids, metric, window_days=days, window_hours=hours,
        align_release=(align == "release"), delta=delta,
        aggregation=aggregation,
    )
    return MsgPackResponse(data, request)


@router.get("/providers")
async def list_providers(
    request: Request,
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    registry = request.app.state.media_registry
    if not await _is_admin(session, guild_id, _user, request):
        enabled = await _get_enabled_providers(session, guild_id)
    else:
        enabled = None
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
        if enabled is None or d.type in enabled
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
    if not await _is_admin(session, guild_id, _user, request) and item["media_type"] not in await _get_enabled_providers(session, guild_id):
        raise HTTPException(status_code=404, detail="Media item not found")
    return MsgPackResponse(item, request)


@router.get("/{media_id}/history")
async def get_media_history(
    request: Request,
    media_id: int,
    metric: str = Query("view_count"),
    days: int = Query(30, ge=1, le=365),
    hours: int | None = Query(None, ge=1, le=48),
    aggregation: str | None = Query(None, pattern=r"^(5min|15min|hourly|daily|weekly|monthly)$"),
    mode: str = Query("total", pattern=r"^(total|delta)$"),
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    item = await media_repo.get(session, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    if not await _is_admin(session, guild_id, _user, request) and item.media_type not in await _get_enabled_providers(session, guild_id):
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
    aggregation: str | None = Query(None, pattern=r"^(5min|15min|hourly|daily|weekly|monthly)$"),
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
            # Handle URL-encoded + (becomes space) and Z suffix
            normalized = date.replace(" ", "+").replace("Z", "+00:00")
            reference_date = datetime.fromisoformat(normalized)
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
    # Normalise timezone: SQLite may return naive datetimes even with timezone=True
    # if they were inserted before timezone-aware code was deployed.
    def _ensure_utc(dt: datetime) -> datetime:
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt

    # Filter snapshots at or before reference_date
    snaps = [s for s in snaps if _ensure_utc(s.fetched_at) <= reference_date]

    # Apply server-side aggregation (reuses the same logic as history endpoint)
    render_snaps: list[Any] = snaps
    render_mode = mode if mode in ("total", "delta") else "total"
    if aggregation:
        agg_mode = render_mode
        aggregated = _aggregate_snapshots(snaps, aggregation, agg_mode)
        render_snaps = [_SnapshotStub(value=d["value"], fetched_at=datetime.fromisoformat(d["fetched_at"])) for d in aggregated]
        render_mode = "total"  # delta already applied by _aggregate_snapshots

    # Determine cache key from the latest snapshot timestamp
    if snaps:
        latest_snap = snaps[-1]
        cache_ts = int(_ensure_utc(latest_snap.fetched_at).timestamp())
    else:
        cache_ts = int(reference_date.timestamp())

    # Determine cache key — includes all params so different metric/range/mode combos don't collide
    range_key = f"h{hours}" if hours is not None else f"d{days}" if days is not None else "all"
    mode_val = mode if mode in ("total", "delta") else "total"
    agg_key = f"_{aggregation}" if aggregation else ""
    cache_dir = CHART_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{media_id}_{metric}_{range_key}{agg_key}_{cache_ts}_{mode_val}.png"

    if cache_path.exists():
        return FileResponse(
            cache_path, media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Compute actual duration for chart title context
    if render_snaps:
        utc_snaps = [_ensure_utc(s.fetched_at) for s in render_snaps]
        duration_hours = (max(utc_snaps) - min(utc_snaps)).total_seconds() / 3600
    else:
        duration_hours = 0.0

    buf = render_media_chart(
        snapshots=render_snaps,
        title=item.title,
        metric_label=metric_label,
        duration_hours=duration_hours,
        mode=render_mode,
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
