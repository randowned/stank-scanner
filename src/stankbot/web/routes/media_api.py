"""User-facing media API — list, detail, history, comparison.

All routes require guild membership. Data comes from the MediaService
which delegates to the provider registry stored on app.state.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.repositories import media as media_repo
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
        media_ids, metric, window_days=days, align_release=(align == "release")
    )
    return MsgPackResponse(data, request)


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
    guild_id: int = Depends(get_active_guild_id),
    _user: dict[str, Any] = Depends(require_guild_member),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    svc = await _media_service(request, session)
    history = await svc.get_metrics_history(media_id, metric, window_days=days)
    return MsgPackResponse({"metric": metric, "days": days, "history": history}, request)
