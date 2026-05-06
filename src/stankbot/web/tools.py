"""Shared FastAPI dependencies — DB sessions, Jinja templates, auth."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.engine import session_scope
from stankbot.db.models import Guild, Player

if TYPE_CHECKING:
    from stankbot.config import AppConfig

log = logging.getLogger(__name__)

_member_cache: dict[tuple[int, int], tuple[float, dict[str, Any] | None]] = {}
_MEMBER_CACHE_TTL = 300
_MEMBER_CACHE_MAXSIZE = 1000


def _evict_expired(now: float) -> None:
    """Remove cache entries whose TTL has passed."""
    stale = [k for k, (ts, _) in _member_cache.items() if now - ts >= _MEMBER_CACHE_TTL]
    for k in stale:
        del _member_cache[k]


def _evict_oldest(count: int) -> None:
    """Remove the ``count`` oldest entries from the cache."""
    if count <= 0:
        return
    sorted_keys = sorted(_member_cache.items(), key=lambda item: item[1][0])
    for k, _ in sorted_keys[:count]:
        del _member_cache[k]


async def fetch_guild_member(
    config: AppConfig, guild_id: int, user_id: int
) -> dict[str, Any] | None:
    """Check if user is a member of guild via Discord API.

    Uses bot token to call GET /guilds/{guild_id}/members/{user_id}.
    Results are cached in-memory for 5 minutes.

    Returns member dict with 'permissions' or None if not found.
    """
    global _member_cache

    cache_key = (guild_id, user_id)
    now = time.time()

    if cache_key in _member_cache:
        ts, cached = _member_cache[cache_key]
        if now - ts < _MEMBER_CACHE_TTL:
            return cached
        del _member_cache[cache_key]

    token = config.discord_token.get_secret_value()
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}",
                headers={"Authorization": f"Bot {token}"},
            )
        if resp.status_code == 404:
            _member_cache[cache_key] = (now, None)
            return None
        if resp.status_code != 200:
            log.warning(
                "fetch_guild_member failed: guild=%d user=%d status=%d",
                guild_id,
                user_id,
                resp.status_code,
            )
            return None

        data = resp.json()

        if len(_member_cache) >= _MEMBER_CACHE_MAXSIZE:
            _evict_expired(now)
        if len(_member_cache) >= _MEMBER_CACHE_MAXSIZE:
            _evict_oldest(len(_member_cache) - _MEMBER_CACHE_MAXSIZE + 1)

        _member_cache[cache_key] = (now, data)
        return data
    except Exception:
        log.exception("fetch_guild_member error: guild=%d user=%d", guild_id, user_id)
        return None


def _is_mock_auth(request: Request) -> bool:
    """Return True when dev mock auth is active."""
    config: AppConfig = request.app.state.config
    return config.env == "dev-mock" and config.mock_auth


def get_templates(request: Request) -> Jinja2Templates:
    templates = getattr(request.app.state, "_templates", None)
    if templates is None:
        templates = Jinja2Templates(
            directory=str(request.app.state.templates_dir),
        )
        request.app.state._templates = templates
    return templates


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with session_scope(factory) as session:
        yield session


def current_user(request: Request) -> dict[str, Any] | None:
    """Returns ``{"id": int, "username": str, "avatar": str}`` or ``None``.

    Populated by :mod:`stankbot.web.routes.auth` after successful OAuth.
    """
    user = request.session.get("user")
    if user is None:
        return None
    return dict(user)


class _LoginRedirect(HTTPException):
    """Carries a RedirectResponse so the app's exception handler can
    send a browser-friendly 302 instead of a JSON 401.
    """

    def __init__(self, response: RedirectResponse) -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
        self.response = response


class _NotInGuild(HTTPException):
    """Carries a 403 TemplateResponse for users who are not guild members."""

    def __init__(self, response: Any) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="not in guild")
        self.response = response


async def _is_guild_member(request: Request, guild_id: int, user_id: int) -> bool:
    """Return True if the user is a member of the given guild (via Discord API)."""
    config: AppConfig = request.app.state.config
    member = await fetch_guild_member(config, guild_id, user_id)
    return member is not None


async def require_login(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            next_url = str(request.url.path)
            if request.url.query:
                next_url += f"?{request.url.query}"
            raise _LoginRedirect(
                RedirectResponse(
                    url=f"/auth/login?next={quote(next_url)}", status_code=302
                )
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="login required"
        )
    return user


async def require_guild_member(request: Request) -> dict[str, Any]:
    """Dependency for public dashboard routes.

    Redirects unauthenticated visitors to ``/`` (which shows the login UI).
    Raises ``_NotInGuild`` (rendered as ``unauthorized.html``) for users who
    are logged in but not a member of the default guild.
    Owner is always allowed even if not a member.
    In dev mock-auth mode, auto-login is assumed.
    """
    if _is_mock_auth(request):
        user = current_user(request)
        if user is not None:
            return user
        config: AppConfig = request.app.state.config
        return {
            "id": config.mock_default_user_id,
            "username": config.mock_default_user_name,
            "avatar": None,
        }
    user = current_user(request)
    if user is None:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            next_url = str(request.url.path)
            if request.url.query:
                next_url += f"?{request.url.query}"
            raise _LoginRedirect(
                RedirectResponse(url=f"/auth/login?next={quote(next_url)}", status_code=302)
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="login required"
        )
    if _is_owner(request):
        return user
    config: AppConfig = request.app.state.config
    default_gid = config.default_guild_id
    uid = int(user["id"])
    is_member = await _is_guild_member(request, default_gid, uid)
    if not is_member:
        templates = get_templates(request)
        raise _NotInGuild(
            templates.TemplateResponse(
                request,
                "unauthorized.html",
                {"request": request, "user": user},
                status_code=403,
            )
        )
    return user


async def guild_name_for(session: AsyncSession, guild_id: int) -> str:
    name = (
        await session.execute(select(Guild.name).where(Guild.id == guild_id))
    ).scalar_one_or_none()
    return name or f"Guild {guild_id}"


async def player_names_for(
    session: AsyncSession, guild_id: int, user_ids: Iterable[int]
) -> dict[int, str]:
    ids = [int(u) for u in user_ids if u is not None]
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Player.user_id, Player.display_name).where(
                Player.guild_id == guild_id, Player.user_id.in_(ids)
            )
        )
    ).all()
    return {int(uid): (name or str(uid)) for uid, name in rows}


def get_guild_id(request: Request) -> int:
    """The configured default guild for the single-guild dashboard."""
    config: AppConfig = request.app.state.config
    return config.default_guild_id


def get_active_guild_id(request: Request) -> int:
    """The guild currently selected in the session (for admin views).

    Returns the session's ``guild_id``, or falls back to the default.
    Keeps a backward-compat read of ``guild`` and ``active_guild_id`` for
    existing sessions that haven't re-logged since the rename.
    """
    config: AppConfig = request.app.state.config
    return (
        request.session.get("guild_id")
        or request.session.get("guild")
        or request.session.get("active_guild_id")
        or config.default_guild_id
    )


def _is_owner(request: Request) -> bool:
    """Check if current user is the bot owner."""
    user = current_user(request)
    if user is None:
        return False
    config: AppConfig = request.app.state.config
    return int(user.get("id", 0)) == int(getattr(config, "owner_id", 0) or 0)


async def require_global_admin(
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_login),
) -> dict[str, Any]:
    """Verify the session-user is a global admin.

    Global admins are: bot owner, or entries in admin_users table (guild_id=0).
    They can access all guilds and see the guild switcher.
    """
    if _is_mock_auth(request):
        if not request.session.get("is_global_admin", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="not a global admin"
            )
        return user

    from stankbot.services.permission_service import PermissionService

    config: AppConfig = request.app.state.config

    if _is_owner(request):
        return user

    svc = PermissionService(session, owner_id=config.owner_id)
    uid = int(user["id"])

    if await svc.is_global_admin(uid):
        return user

    templates = get_templates(request)
    raise _NotInGuild(
        templates.TemplateResponse(
            request,
            "unauthorized.html",
            {"request": request, "user": user},
            status_code=403,
        )
    )


async def require_guild_admin(
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_login),
) -> dict[str, Any]:
    """Verify the session-user is an admin of the active guild.

    Owner (config.owner_id) is always admin.
    Global admins (in admin_users table) have access to all guilds.
    Guild admins (in admin_roles for the guild) have access to that guild.
    In dev mock-auth mode, respects session flags (is_global_admin / is_guild_admin).
    """
    if _is_mock_auth(request):
        if not (request.session.get("is_global_admin", True) or request.session.get("is_guild_admin", True)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="not a guild admin"
            )
        return user

    from stankbot.services.permission_service import PermissionService

    config: AppConfig = request.app.state.config
    guild_id = get_active_guild_id(request)

    def _unauthorized() -> _NotInGuild:
        templates = get_templates(request)
        return _NotInGuild(
            templates.TemplateResponse(
                request,
                "unauthorized.html",
                {"request": request, "user": user},
                status_code=403,
            )
        )

    if _is_owner(request):
        return user

    svc = PermissionService(session, owner_id=config.owner_id)
    uid = int(user["id"])

    is_global = await svc.is_global_admin(uid)
    if is_global:
        return user

    if await svc.is_guild_admin(guild_id, uid):
        return user

    config: AppConfig = request.app.state.config
    member = await fetch_guild_member(config, guild_id, uid)
    if member is None:
        raise _unauthorized()

    perms = int(member.get("permissions", 0))
    has_manage_guild = bool(perms & 0x20)
    if has_manage_guild:
        return user

    raise _unauthorized()
