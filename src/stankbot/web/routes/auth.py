"""Discord OAuth2 login flow.

Scopes requested: ``identify`` (so we know who logged in) + ``guilds``
(so we can tell which servers they're in, and which they admin).

On callback we stash a compact profile + the guild list into the
signed Starlette session cookie. Admin checks in :mod:`web.deps` read
the permissions integer out of that cached guild list.

In ``ENV=dev`` with ``mock_auth=true``, the OAuth flow is bypassed in
favour of automatic dev-login so you can open the dashboard without a
real Discord account.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from stankbot.web.tools import get_config, require_login

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _is_safe_redirect(url: str) -> bool:
    """Return True only for relative paths with no scheme or host component.

    Rejects protocol-relative URLs like ``//evil.com`` that start with ``/``
    but resolve to an external host.
    """
    parsed = urlparse(url)
    return url.startswith("/") and not parsed.scheme and not parsed.netloc


_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
_TOKEN_URL = "https://discord.com/api/oauth2/token"
_API_BASE = "https://discord.com/api/v10"

_DEFAULT_MOCK_GUILDS = [
    {
        "id": 123456789,
        "name": "Dev Server",
        "icon": None,
        "permissions": 0x20,
    }
]


@router.get("/login")
async def login(
    request: Request,
    next: str | None = None,
    config=Depends(get_config),
) -> RedirectResponse:
    if config.env == "dev" and config.mock_auth:
        target = f"/auth/mock-login?next={quote(next or '/')}" if next else "/auth/mock-login"
        return RedirectResponse(target, status_code=302)

    if config.oauth_client_secret is None:
        raise HTTPException(
            status_code=503,
            detail="OAuth not configured — set OAUTH_CLIENT_SECRET.",
        )
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    if next and _is_safe_redirect(next):
        request.session["oauth_next"] = next
    params = {
        "client_id": str(config.discord_app_id),
        "redirect_uri": config.oauth_redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
        "prompt": "none",
    }
    return RedirectResponse(f"{_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    config=Depends(get_config),
) -> RedirectResponse:
    expected = request.session.pop("oauth_state", None)
    if not state or state != expected:
        raise HTTPException(status_code=400, detail="state mismatch")
    if code is None:
        raise HTTPException(status_code=400, detail="missing code")
    if config.oauth_client_secret is None:
        raise HTTPException(status_code=503, detail="OAuth not configured")

    data = {
        "client_id": str(config.discord_app_id),
        "client_secret": config.oauth_client_secret.get_secret_value(),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.oauth_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        tok = await client.post(
            _TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if tok.status_code != 200:
            log.warning("oauth token exchange failed: %s %s", tok.status_code, tok.text)
            raise HTTPException(status_code=400, detail="token exchange failed")
        access_token = tok.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        me_resp = await client.get(f"{_API_BASE}/users/@me", headers=headers)
        guilds_resp = await client.get(f"{_API_BASE}/users/@me/guilds", headers=headers)

    if me_resp.status_code != 200 or guilds_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="failed fetching profile")

    me: dict[str, Any] = me_resp.json()
    guilds: list[dict[str, Any]] = guilds_resp.json()

    request.session["user"] = {
        "id": int(me["id"]),
        "username": me.get("global_name") or me.get("username") or str(me["id"]),
        "avatar": me.get("avatar"),
    }
    request.session["guilds"] = [
        {
            "id": int(g["id"]),
            "name": g.get("name", ""),
            "icon": g.get("icon"),
            "permissions": int(g.get("permissions", 0)),
        }
        for g in guilds
    ]
    request.session["guild"] = config.default_guild_id
    target = request.session.pop("oauth_next", None) or "/"
    return RedirectResponse(target, status_code=303)


@router.get("/mock-login")
async def mock_login_get(
    request: Request,
    next: str | None = None,
    config=Depends(get_config),
) -> RedirectResponse:
    """Auto-login for dev mode — creates a session as the default dev user."""
    if config.env != "dev":
        raise HTTPException(status_code=403, detail="Mock auth only available in dev mode")

    request.session["user"] = {
        "id": config.mock_default_user_id,
        "username": config.mock_default_user_name,
        "avatar": None,
    }
    guild_id = config.mock_default_guild_id or config.default_guild_id
    request.session["guilds"] = [
        {
            "id": guild_id,
            "name": config.mock_default_guild_name,
            "icon": None,
            "permissions": 0x20,
        }
    ]
    request.session["guild"] = guild_id
    target = next if next and _is_safe_redirect(next) else "/"
    return RedirectResponse(target, status_code=303)


@router.post("/mock-login")
async def mock_login_post(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    """Programmatic mock login for Playwright and testing.

    Accepts a JSON body to override the default dev user.
    """
    if config.env != "dev":
        raise HTTPException(status_code=403, detail="Mock auth only available in dev mode")

    body = await request.json()
    user_id = body.get("user_id", config.mock_default_user_id)
    username = body.get("username", config.mock_default_user_name)
    avatar = body.get("avatar", None)
    guilds = body.get("guilds", _DEFAULT_MOCK_GUILDS)
    guild_id = body.get("guild", body.get("active_guild_id", guilds[0]["id"] if guilds else config.default_guild_id))
    is_admin = body.get("is_admin", True)

    request.session["user"] = {
        "id": int(user_id),
        "username": username,
        "avatar": avatar,
    }
    request.session["guilds"] = [
        {
            "id": int(g["id"]),
            "name": g.get("name", ""),
            "icon": g.get("icon"),
            "permissions": int(g.get("permissions", 0x20 if is_admin else 0)),
        }
        for g in guilds
    ]
    request.session["guild"] = int(guild_id)
    return JSONResponse({"success": True})


@router.get("")
async def auth_check(request: Request, user: dict = Depends(require_login)) -> JSONResponse:
    """Return current user info for SvelteKit authentication."""
    return JSONResponse(
        {
            "id": str(user["id"]),
            "username": user.get("username", ""),
            "avatar": user.get("avatar"),
        }
    )


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
