"""Spotify OAuth2 flow — bot owner connects their personal Spotify account.

PKCE (S256) Authorization Code flow. The resulting refresh_token is stored
in the guild_settings table under Keys.SPOTIFY_REFRESH_TOKEN so the
SpotifyProvider can use it for Partner API playcount queries.

All routes are gated on the bot owner (owner_id from config), not just
admin — only the bot owner can connect their personal Spotify account.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.services.settings_service import Keys, SettingsService
from stankbot.web.tools import get_config, get_db
from stankbot.web.transport import MsgPackResponse

router = APIRouter(tags=["spotify-oauth"])
log = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"

# Minimal scope — only need a valid user token for Partner API
_SCOPES = ["user-read-private"]

# PKCE verifier stored in session cookie per auth attempt
_SESSION_KEY_VERIFIER = "spotify_pkce_verifier"
_SESSION_KEY_REDIRECT = "spotify_oauth_redirect"


def _owner_only(request: Request) -> None:
    """Raise 403 unless the authenticated user equals the bot owner."""
    config = get_config(request)
    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if int(user.get("id", 0)) != config.owner_id:
        raise HTTPException(status_code=403, detail="Only the bot owner can connect Spotify")


# ----------------------------------------------------------------
# OAuth login
# ----------------------------------------------------------------


@router.get("/auth/spotify/login")
async def spotify_login(
    request: Request,
    redirect_to: str = "/admin/settings",
) -> RedirectResponse:
    """Start Spotify OAuth PKCE flow (bot owner only)."""
    _owner_only(request)

    config = request.app.state.config
    client_id = config.spotify_client_id
    if client_id is None:
        raise HTTPException(status_code=400, detail="SPOTIFY_CLIENT_ID is not configured")

    # Generate PKCE code verifier + challenge
    verifier = secrets.token_urlsafe(64)
    sha256 = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(sha256).rstrip(b"=").decode()

    request.session[_SESSION_KEY_VERIFIER] = verifier
    request.session[_SESSION_KEY_REDIRECT] = redirect_to

    params = {
        "client_id": client_id.get_secret_value(),
        "response_type": "code",
        "redirect_uri": config.spotify_oauth_redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": " ".join(_SCOPES),
        "state": secrets.token_urlsafe(16),
    }
    url = f"{_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


# ----------------------------------------------------------------
# OAuth callback
# ----------------------------------------------------------------


@router.get("/auth/spotify/callback")
async def spotify_callback(
    request: Request,
    code: str,
    state: str = "",
    error: str = "",
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Spotify OAuth callback — exchange code for tokens, store refresh_token."""
    if error:
        log.warning("Spotify OAuth error: %s", error)
        raise HTTPException(status_code=400, detail=f"Spotify returned an error: {error}")

    verifier = request.session.get(_SESSION_KEY_VERIFIER)
    redirect_to = request.session.get(_SESSION_KEY_REDIRECT, "/admin/settings")
    request.session.pop(_SESSION_KEY_VERIFIER, None)
    request.session.pop(_SESSION_KEY_REDIRECT, None)

    if not verifier:
        raise HTTPException(status_code=400, detail="Missing PKCE verifier — restart the login flow")

    config = request.app.state.config
    client_id = config.spotify_client_id
    client_secret = config.spotify_client_secret

    if client_id is None or client_secret is None:
        raise HTTPException(status_code=400, detail="Spotify client credentials not configured")

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.spotify_oauth_redirect_uri,
                "code_verifier": verifier,
            },
            auth=(client_id.get_secret_value(), client_secret.get_secret_value()),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )

    if resp.status_code != 200:
        try:
            body = resp.text
        except Exception:
            body = "<unreadable>"
        log.warning("Spotify OAuth token exchange failed: %d — %s", resp.status_code, body[:300])
        raise HTTPException(status_code=400, detail="Failed to exchange Spotify authorization code")

    data: dict[str, Any] = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        log.warning("Spotify OAuth: no refresh_token in response — %s", data.keys())
        raise HTTPException(status_code=400, detail="Spotify did not return a refresh token")

    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    guild_id = request.session.get("guild_id")
    if not guild_id:
        raise HTTPException(status_code=400, detail="No guild selected")

    # Store refresh token in guild_settings
    svc = SettingsService(session)
    await svc.set(int(guild_id), Keys.SPOTIFY_REFRESH_TOKEN, refresh_token)

    log.info("Spotify OAuth: stored refresh_token for guild=%s", guild_id)
    return RedirectResponse(redirect_to or "/admin/settings", status_code=302)


# ----------------------------------------------------------------
# Status & disconnect
# ----------------------------------------------------------------


@router.get("/api/admin/spotify/status")
async def spotify_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    """Return Spotify connection status (bot owner only)."""
    _owner_only(request)

    guild_id = request.session.get("guild_id")
    if not guild_id:
        return MsgPackResponse({"connected": False}, request)

    svc = SettingsService(session)
    token = await svc.get(int(guild_id), Keys.SPOTIFY_REFRESH_TOKEN, None)
    connected = token is not None and isinstance(token, str) and bool(token.strip())

    return MsgPackResponse({"connected": connected}, request)


@router.post("/api/admin/spotify/disconnect")
async def spotify_disconnect(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MsgPackResponse:
    """Disconnect Spotify — remove stored refresh_token (bot owner only)."""
    _owner_only(request)

    guild_id = request.session.get("guild_id")
    if not guild_id:
        raise HTTPException(status_code=400, detail="No guild selected")

    svc = SettingsService(session)
    await svc.set(int(guild_id), Keys.SPOTIFY_REFRESH_TOKEN, "")

    log.info("Spotify: disconnected for guild=%s", guild_id)
    return MsgPackResponse({"connected": False}, request)
