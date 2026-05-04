"""Spotify auth routes — sp_dc cookie management for Partner API access.

The bot owner sets their spotify.com `sp_dc` cookie via the media settings modal.
The provider exchanges it for Partner API access tokens (which get RBAC).
All routes are gated on the bot owner (owner_id from config).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.services.settings_service import Keys, SettingsService
from stankbot.web.tools import get_config, get_db
from stankbot.web.transport import MsgPackResponse, msgpack_body

router = APIRouter(tags=["spotify-oauth"])
log = logging.getLogger(__name__)


class SetSpDcPayload(BaseModel):
    access_token: str


def _owner_only(request: Request) -> None:
    """Raise 403 unless the authenticated user equals the bot owner."""
    config = get_config(request)
    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if int(user.get("id", 0)) != config.owner_id:
        raise HTTPException(status_code=403, detail="Only the bot owner can manage Spotify auth")


def _get_provider(request: Request):
    registry = request.app.state.media_registry
    return registry.get("spotify")


# ----------------------------------------------------------------
# Set sp_dc cookie
# ----------------------------------------------------------------


@router.post("/api/admin/spotify/set-sp-dc")
async def set_sp_dc(
    request: Request,
    payload: SetSpDcPayload = msgpack_body(SetSpDcPayload),  # type: ignore[assignment]
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    """Store the sp_dc cookie value for Partner API token exchange (bot owner only)."""
    _owner_only(request)

    access_token = payload.access_token.strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Access token is required")

    guild_id = request.session.get("guild_id")
    if not guild_id:
        raise HTTPException(status_code=400, detail="No guild selected")

    # Store in DB
    svc = SettingsService(session)
    await svc.set(int(guild_id), Keys.SPOTIFY_SP_DC, access_token)

    # Also set on the in-memory provider so it takes effect immediately
    provider = _get_provider(request)
    if provider is not None and hasattr(provider, "set_sp_dc"):
        provider.set_sp_dc(access_token)

    log.info("Spotify: access token stored for guild=%s", guild_id)
    return MsgPackResponse({"ok": True, "status": "set"}, request)


# ----------------------------------------------------------------
# Status
# ----------------------------------------------------------------


@router.get("/api/admin/spotify/status")
async def spotify_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    """Return Spotify connection status (bot owner only).

    Status values:
      - "not-set"   — no access token stored
      - "set"       — access token stored
    """
    _owner_only(request)

    guild_id = request.session.get("guild_id")
    if not guild_id:
        return MsgPackResponse({"connected": False, "status": "not-set"}, request)

    svc = SettingsService(session)
    token = await svc.get(int(guild_id), Keys.SPOTIFY_SP_DC, None)
    has_token = token is not None and isinstance(token, str) and bool(token.strip())

    return MsgPackResponse(
        {"connected": has_token, "status": "set" if has_token else "not-set"},
        request,
    )


# ----------------------------------------------------------------
# Disconnect
# ----------------------------------------------------------------


@router.post("/api/admin/spotify/disconnect")
async def spotify_disconnect(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    """Clear sp_dc cookie (bot owner only)."""
    _owner_only(request)

    guild_id = request.session.get("guild_id")
    if not guild_id:
        raise HTTPException(status_code=400, detail="No guild selected")

    svc = SettingsService(session)
    await svc.set(int(guild_id), Keys.SPOTIFY_SP_DC, "")

    provider = _get_provider(request)
    if provider is not None and hasattr(provider, "set_sp_dc"):
        provider.set_sp_dc("")

    log.info("Spotify: disconnected for guild=%s", guild_id)
    return MsgPackResponse({"connected": False, "status": "not-set"}, request)
