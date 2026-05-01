"""Admin media API — manage media items and metrics.

All routes require guild admin. Delegates to MediaService.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.repositories import audit_log as audit_repo
from stankbot.services.media_service import MediaService
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.web.tools import get_active_guild_id, get_db, require_guild_admin
from stankbot.web.transport import MsgPackResponse, msgpack_body

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/media", tags=["admin-media"])


def _ok(request: Request, extra: dict[str, Any] | None = None) -> MsgPackResponse:
    body: dict[str, Any] = {"success": True}
    if extra:
        body.update(extra)
    return MsgPackResponse(body, request)


async def _media_service(
    request: Request,
    session: AsyncSession,
) -> MediaService:
    registry = request.app.state.media_registry
    return MediaService(session=session, registry=registry)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("")
async def list_media_admin(
    request: Request,
    guild_id: int = Depends(get_active_guild_id),
    _admin: dict[str, Any] = Depends(require_guild_admin),
    media_type: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    svc = await _media_service(request, session)
    items = await svc.list_media(guild_id, media_type)
    return MsgPackResponse({"items": items}, request)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_providers(
    request: Request,
    guild_id: int = Depends(get_active_guild_id),
    _admin: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    registry = request.app.state.media_registry
    defs = [d for d in registry.all_defs()]
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
        for d in defs
    ]
    return MsgPackResponse({"providers": providers}, request)


# ---------------------------------------------------------------------------
# Add
# ---------------------------------------------------------------------------


class AddMediaPayload(BaseModel):
    media_type: str
    external_id: str
    slug: str | None = None


@router.post("")
async def add_media(
    request: Request,
    payload: AddMediaPayload = msgpack_body(AddMediaPayload),  # type: ignore[assignment]
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    registry = request.app.state.media_registry
    provider = registry.get(payload.media_type)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unknown media type: {payload.media_type}")
    if not provider.is_configured():
        raise HTTPException(
            status_code=400, detail=f"Provider not configured: {payload.media_type}"
        )

    svc = MediaService(session=session, registry=registry)

    # Pre-validate: distinguish bad URL from auth/API failure
    if hasattr(provider, "extract_id") and provider.extract_id(payload.external_id) is None:
        raise HTTPException(status_code=400, detail="Could not parse the URL/URI. Use a Spotify URL like https://open.spotify.com/track/... or spotify:track:...")
    resolved = await provider.resolve(payload.external_id)
    if resolved is None:
        raise HTTPException(status_code=400, detail="Could not resolve the given URL/ID. Check that your provider credentials are valid and the item exists.")

    item = await svc.add_resolved_media(
        guild_id=guild_id,
        media_type=payload.media_type,
        resolved=resolved,
        added_by=int(user["id"]),
        slug=payload.slug,
    )
    if item is None:
        raise HTTPException(status_code=409, detail="This media item has already been added (duplicate URL/ID).")

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.add",
        payload={"media_type": payload.media_type, "external_id": payload.external_id},
    )

    return MsgPackResponse(item, request, status_code=201)


# ---------------------------------------------------------------------------
# Single item operations
# ---------------------------------------------------------------------------


@router.get("/{media_id}")
async def get_media_admin(
    request: Request,
    media_id: int,
    guild_id: int = Depends(get_active_guild_id),
    _admin: dict[str, Any] = Depends(require_guild_admin),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    svc = await _media_service(request, session)
    item = await svc.get_media_item(media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    return MsgPackResponse(item, request)


@router.delete("/{media_id}")
async def delete_media(
    request: Request,
    media_id: int,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    svc = MediaService(session=session, registry=request.app.state.media_registry)
    deleted = await svc.delete_media(media_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Media item not found")

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.delete",
        payload={"media_item_id": media_id},
    )
    return _ok(request)


@router.post("/{media_id}/refresh")
async def refresh_single(
    request: Request,
    media_id: int,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    svc = MediaService(session=session, registry=request.app.state.media_registry)
    result = await svc.refresh_single(media_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    if result.error:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {result.error}")

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.refresh",
        payload={"media_item_id": media_id},
    )
    return _ok(request, {"metrics": result.values})


@router.post("/refresh-all")
async def refresh_all(
    request: Request,
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    svc = MediaService(session=session, registry=request.app.state.media_registry)
    result = await svc.refresh_all(guild_id)

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.refresh_all",
        payload={"refreshed": result.refreshed, "failed": result.failed},
    )
    return _ok(
        request,
        {
            "refreshed": result.refreshed,
            "failed": result.failed,
            "errors": result.errors[:10],
        },
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class MediaSettingsPayload(BaseModel):
    update_interval_minutes: int = Field(ge=5, le=1440, default=10)


@router.post("/settings")
async def update_media_settings(
    request: Request,
    payload: MediaSettingsPayload = msgpack_body(MediaSettingsPayload),  # type: ignore[assignment]
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    svc = SettingsService(session)
    await svc.set(guild_id, Keys.MEDIA_METRICS_UPDATE_INTERVAL_MINUTES, payload.update_interval_minutes)

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.settings",
        payload={"update_interval_minutes": payload.update_interval_minutes},
    )
    return _ok(request)
