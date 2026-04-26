"""Discord OAuth2 login flow.

Scopes requested: ``identify`` (so we know who logged in).

On callback we stash a compact profile into the signed Starlette session cookie.
Guild membership is verified via Discord API at request time.

In ``ENV=dev-mock`` with ``mock_auth=true``, the OAuth flow is bypassed in
favour of automatic dev-login so you can open the dashboard without a
real Discord account.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from stankbot.web.tools import get_config
from stankbot.web.transport import MsgPackResponse

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
_TOKEN_URL = "https://discord.com/api/oauth2/token"
_API_BASE = "https://discord.com/api/v10"


@router.get("/login")
async def login(
    request: Request,
    config=Depends(get_config),
) -> RedirectResponse:
    if config.env == "dev-mock" and config.mock_auth:
        next_url = request.query_params.get("next", "/")
        return RedirectResponse(f"/auth/mock-login?next={next_url}", status_code=302)

    if config.oauth_client_secret is None:
        raise HTTPException(
            status_code=503,
            detail="OAuth not configured — set OAUTH_CLIENT_SECRET.",
        )
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    next_url = request.query_params.get("next")
    params = {
        "client_id": str(config.discord_app_id),
        "redirect_uri": config.oauth_redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "none",
    }
    if next_url:
        params["state"] = f"{state}?next={next_url}"
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

    if me_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="failed fetching profile")

    me: dict[str, Any] = me_resp.json()

    request.session["user"] = {
        "id": int(me["id"]),
        "username": me.get("global_name") or me.get("username") or str(me["id"]),
        "avatar": me.get("avatar"),
    }
    request.session["guild_id"] = config.default_guild_id
    return RedirectResponse("/", status_code=303)


@router.get("/mock-login")
async def mock_login_get(
    request: Request,
    config=Depends(get_config),
) -> RedirectResponse:
    """Auto-login for dev mode — creates a session as the default dev user."""
    if config.env != "dev-mock":
        raise HTTPException(status_code=403, detail="Mock auth only available in dev mode")

    request.session["user"] = {
        "id": config.mock_default_user_id,
        "username": config.mock_default_user_name,
        "avatar": None,
    }
    guild_id = config.mock_default_guild_id or config.default_guild_id
    request.session["guild_id"] = guild_id
    return RedirectResponse("/", status_code=303)


@router.post("/mock-login")
async def mock_login_post(
    request: Request,
    config=Depends(get_config),
) -> MsgPackResponse:
    """Programmatic mock login for Playwright and testing.

    Accepts a JSON body to override the default dev user.
    """
    if config.env != "dev-mock":
        raise HTTPException(status_code=403, detail="Mock auth only available in dev mode")

    body = await request.json()
    user_id = body.get("user_id", config.mock_default_user_id)
    username = body.get("username", config.mock_default_user_name)
    avatar = body.get("avatar", None)
    guild_id = body.get("guild", body.get("active_guild_id", config.mock_default_guild_id or config.default_guild_id))
    is_global_admin = body.get("is_global_admin", True)
    is_guild_admin = body.get("is_guild_admin", True)

    request.session["user"] = {
        "id": int(user_id),
        "username": username,
        "avatar": avatar,
    }
    request.session["guild_id"] = int(guild_id)
    request.session["is_global_admin"] = bool(is_global_admin)
    request.session["is_guild_admin"] = bool(is_guild_admin)
    return MsgPackResponse({"success": True}, request)


@router.get("")
async def auth_check(request: Request) -> MsgPackResponse:
    """Return current user info + admin status, or null if not authenticated."""
    from stankbot.services.permission_service import PermissionService
    from stankbot.web.tools import (
        current_user,
        get_active_guild_id,
    )

    user = current_user(request)
    if user is None:
        return MsgPackResponse(None, request)

    config = request.app.state.config
    guild_id = get_active_guild_id(request)
    uid = int(user["id"])

    bot_guilds = getattr(request.app.state, "bot_guilds", [])
    guild_name = None
    for g in bot_guilds:
        if int(g.get("id", 0)) == guild_id:
            guild_name = g.get("name")
            break

    is_global_admin = False
    is_guild_admin = False
    if config.env != "dev-mock":
        factory = request.app.state.session_factory
        async with factory() as session:
            svc = PermissionService(session, owner_id=config.owner_id)
            is_global_admin = await svc.is_global_admin(uid)
            if is_global_admin:
                is_guild_admin = True
            else:
                is_guild_admin = await svc.is_guild_admin(guild_id, uid)
    else:
        is_global_admin = request.session.get("is_global_admin", True)
        is_guild_admin = request.session.get("is_guild_admin", True)

    return MsgPackResponse(
        {
            "user": {
                "id": str(user["id"]),
                "username": user.get("username", ""),
                "avatar": user.get("avatar"),
            },
            "guild_id": str(guild_id),
            "guild_name": guild_name,
            "is_admin": is_global_admin or is_guild_admin,
            "is_global_admin": is_global_admin,
        },
        request,
    )


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
