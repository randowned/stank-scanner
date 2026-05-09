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
from stankbot.db.repositories import media as media_repo
from stankbot.services.announcement_service import broadcast_media_milestone
from stankbot.services.embed_builders import build_media_milestone_embed
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
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    from stankbot.services.settings_service import Keys, SettingsService

    registry = request.app.state.media_registry
    settings = SettingsService(session)
    enabled: list[str] = await settings.get(guild_id, Keys.MEDIA_PROVIDERS_ENABLED, ["youtube", "spotify"])
    defs = [d for d in registry.all_defs() if d.type in enabled]
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
    name: str | None = None


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
        name=payload.name,
    )
    if item is None:
        raise HTTPException(status_code=409, detail="This media item has already been added (duplicate URL/ID).")

    # Fetch metrics immediately so the user sees data without waiting for the scheduler
    media_id = item["id"]
    result = await svc.refresh_single(media_id)

    # Get cached metrics for the audit log
    initial_metrics: dict[str, Any] | None = None
    if result.refreshed > 0:
        cached = await media_repo.get_metric_cache(session, media_id)
        initial_metrics = {k: v.get("value") for k, v in cached.items() if isinstance(v, dict)}

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.add",
        payload={
            "media_type": payload.media_type,
            "external_id": payload.external_id,
            "media_id": media_id,
            "initial_metrics": initial_metrics,
        },
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


class UpdateMediaPayload(BaseModel):
    name: str | None = None


@router.patch("/{media_id}")
async def update_media(
    request: Request,
    media_id: int,
    payload: UpdateMediaPayload = msgpack_body(UpdateMediaPayload),  # type: ignore[assignment]
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    svc = MediaService(session=session, registry=request.app.state.media_registry)
    item = await svc.update_name(media_id, payload.name)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.update",
        payload={"media_id": media_id, "name": payload.name},
    )
    return MsgPackResponse(item, request)


@router.get("/{media_id}/snapshots")
async def get_media_snapshots(
    request: Request,
    media_id: int,
    limit: int = Query(20, ge=1, le=100),
    _admin: dict[str, Any] = Depends(require_guild_admin),
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    item = await media_repo.get(session, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    snapshots = await media_repo.get_metric_snapshots_pivoted(session, media_id, limit)
    # Include metric definitions for column labels
    registry = request.app.state.media_registry
    provider = registry.get(item.media_type)
    metric_defs = [
        {"key": m.key, "label": m.label, "format": m.format}
        for m in provider.metrics
    ] if provider else []
    return MsgPackResponse(
        {"snapshots": snapshots, "metric_defs": metric_defs}, request
    )


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
    if result.failed:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {result.errors[0] if result.errors else 'Unknown error'}")

    await audit_repo.append(
        session,
        guild_id=guild_id,
        actor_id=int(user["id"]),
        action="media.refresh",
        payload={"media_item_id": media_id},
    )

    # Milestone announcements
    await _broadcast_milestones(request, session, guild_id, result.milestones)

    return _ok(request, {"refreshed": result.refreshed, "errors": result.errors[:10]})


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

    # Milestone announcements
    await _broadcast_milestones(request, session, guild_id, result.milestones)

    return _ok(
        request,
        {
            "refreshed": result.refreshed,
            "failed": result.failed,
            "errors": result.errors[:10],
            "milestones": len(result.milestones),
        },
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class MediaSettingsPayload(BaseModel):
    youtube_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    spotify_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    replies_ephemeral: bool | None = None
    admin_only: bool | None = None
    providers_enabled: list[str] | None = None
    announce_milestones: bool | None = None
    announce_channel_id: int | None = None


@router.post("/settings")
async def update_media_settings(
    request: Request,
    payload: MediaSettingsPayload = msgpack_body(MediaSettingsPayload),  # type: ignore[assignment]
    session: AsyncSession = Depends(get_db),
    guild_id: int = Depends(get_active_guild_id),
    user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    svc = SettingsService(session)
    audit_payload: dict[str, Any] = {}
    if payload.youtube_interval_minutes is not None:
        await svc.set(guild_id, Keys.MEDIA_YOUTUBE_UPDATE_INTERVAL_MINUTES, payload.youtube_interval_minutes)
        audit_payload["youtube_interval"] = payload.youtube_interval_minutes
    if payload.spotify_interval_minutes is not None:
        await svc.set(guild_id, Keys.MEDIA_SPOTIFY_UPDATE_INTERVAL_MINUTES, payload.spotify_interval_minutes)
        audit_payload["spotify_interval"] = payload.spotify_interval_minutes

    # Resync scheduler so the new intervals take effect immediately
    bot = getattr(request.app.state, "bot", None)
    if bot is not None and hasattr(bot, "media_scheduler"):
        if payload.youtube_interval_minutes is not None:
            await bot.media_scheduler.sync_guild(guild_id, "youtube")
        if payload.spotify_interval_minutes is not None:
            await bot.media_scheduler.sync_guild(guild_id, "spotify")
    if payload.replies_ephemeral is not None:
        await svc.set(guild_id, Keys.MEDIA_REPLIES_EPHEMERAL, payload.replies_ephemeral)
        audit_payload["replies_ephemeral"] = payload.replies_ephemeral
    if payload.admin_only is not None:
        await svc.set(guild_id, Keys.MEDIA_REPLIES_ADMIN_ONLY, payload.admin_only)
        audit_payload["admin_only"] = payload.admin_only
    if payload.providers_enabled is not None:
        await svc.set(guild_id, Keys.MEDIA_PROVIDERS_ENABLED, payload.providers_enabled)
        audit_payload["providers_enabled"] = payload.providers_enabled
        bot = getattr(request.app.state, "bot", None)
        if bot is not None and hasattr(bot, "media_scheduler"):
            await bot.media_scheduler.sync_guild(guild_id)
    if payload.announce_milestones is not None:
        await svc.set(guild_id, Keys.MEDIA_ANNOUNCE_MILESTONES, payload.announce_milestones)
        audit_payload["announce_milestones"] = payload.announce_milestones
    if payload.announce_channel_id is not None:
        await svc.set(guild_id, Keys.MEDIA_ANNOUNCE_CHANNEL_ID, payload.announce_channel_id)
        audit_payload["announce_channel_id"] = payload.announce_channel_id

    if audit_payload:
        await audit_repo.append(
            session,
            guild_id=guild_id,
            actor_id=int(user["id"]),
            action="media.settings",
            payload=audit_payload,
        )
    return _ok(request)


@router.post("/backfill-alignment-mask")
async def backfill_alignment_mask(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(require_guild_admin),
) -> MsgPackResponse:
    """Recompute alignment_mask on every snapshot row (including previously set values)."""
    from stankbot.services.media_service import MediaService
    registry = request.app.state.media_registry
    svc = MediaService(session=session, registry=registry)
    updated = await svc.backfill_alignment_masks()
    return MsgPackResponse({"updated": updated}, request)


async def _broadcast_milestones(
    request: Request,
    session: AsyncSession,
    guild_id: int,
    milestones: list[Any],
) -> None:
    if not milestones:
        return
    settings_svc = SettingsService(session)
    milestones_enabled = await settings_svc.get(guild_id, Keys.MEDIA_ANNOUNCE_MILESTONES, True)
    if not milestones_enabled:
        return
    media_channel = await settings_svc.get(guild_id, Keys.MEDIA_ANNOUNCE_CHANNEL_ID, None)
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        return

    registry = request.app.state.media_registry
    base_url = bot.config.oauth_redirect_uri.rsplit("/", 2)[0]

    for minfo in milestones:
        other_parts: list[str] = []
        cache = await media_repo.get_metric_cache(session, minfo.media_item_id)
        provider = registry.get(minfo.media_type)
        if provider:
            for mdef in provider.metrics:
                if mdef.key == minfo.metric_key:
                    continue
                mv = cache.get(mdef.key, {})
                if isinstance(mv, dict) and int(mv.get("value", 0)):
                    other_parts.append(f"{mdef.icon} {_fmt_compact_media(int(mv['value']))}")
        other_metrics = "  \u00b7  ".join(other_parts) if other_parts else "\u2014"

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
            bot,
            guild_id=guild_id,
            embed=embed,
            media_announce_channel_id=media_channel,
            milestones_enabled=True,
        )
        log.info(
            "MediaMilestone: guild=%d item=%d metric=%s milestone=%s announced via admin refresh",
            guild_id, minfo.media_item_id, minfo.metric_key,
            f"{minfo.milestone_value:,}",
        )


def _fmt_compact_media(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B".replace(".0B", "B")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(n)
