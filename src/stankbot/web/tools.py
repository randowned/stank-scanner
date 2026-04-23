"""Shared FastAPI dependencies — DB sessions, Jinja templates, auth."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.engine import session_scope
from stankbot.db.models import Guild, Player

if TYPE_CHECKING:
    from stankbot.config import AppConfig


def _is_mock_auth(request: Request) -> bool:
    """Return True when dev mock auth is active."""
    config: AppConfig = request.app.state.config
    return config.env == "dev" and config.mock_auth


def _is_admin_from_session(request: Request) -> bool:
    """Cookie-based admin check for nav rendering.

    Mirrors the MANAGE_GUILD + owner paths in ``require_guild_admin`` but
    skips the DB-configured admin extras so this can run synchronously in
    a Jinja context processor. Owner is always admin. For non-owners:
    checks MANAGE_GUILD permission in the active guild.
    """
    if _is_mock_auth(request):
        return True
    user = current_user(request)
    if user is None:
        return False
    if _is_owner(request):
        return True
    guild_id = get_active_guild_id(request)
    guilds = request.session.get("guilds", [])
    match = next((g for g in guilds if int(g.get("id", 0)) == guild_id), None)
    if match is None:
        return False
    perms = int(match.get("permissions", 0))
    return bool(perms & 0x20)


def _admin_context(request: Request) -> dict[str, Any]:
    bot_guilds: list[dict[str, object]] = getattr(request.app.state, "bot_guilds", [])
    user_guild_ids = {int(g.get("id", 0)) for g in request.session.get("guilds", [])}
    return {
        "is_admin": _is_admin_from_session(request),
        "is_owner": _is_owner(request),
        "active_guild_id": get_active_guild_id(request),
        "bot_guilds": [
            {
                "id": g["id"],
                "name": g["name"],
                "icon": g.get("icon"),
                "in_oauth": g["id"] in user_guild_ids,
            }
            for g in bot_guilds
        ],
    }


def get_templates(request: Request) -> Jinja2Templates:
    templates = getattr(request.app.state, "_templates", None)
    if templates is None:
        templates = Jinja2Templates(
            directory=str(request.app.state.templates_dir),
            context_processors=[_admin_context],
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


def _is_guild_member(request: Request, guild_id: int) -> bool:
    """Return True if the session user is a member of the given guild."""
    guilds = request.session.get("guilds", [])
    return any(int(g.get("id", 0)) == guild_id for g in guilds)


def require_login(request: Request) -> dict[str, Any]:
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


def require_guild_member(request: Request) -> dict[str, Any]:
    """Dependency for public dashboard routes.

    Redirects unauthenticated visitors to ``/`` (which shows the login UI).
    Raises ``_NotInGuild`` (rendered as ``unauthorized.html``) for users who
    are logged in but not a member of the configured guild.
    Owner is always allowed even if not a member.
    In dev mock-auth mode, auto-login is assumed.
    """
    if _is_mock_auth(request):
        user = current_user(request)
        if user is not None:
            return user
        # Fabricate a mock user on the fly for routes that don't pre-login.
        config: AppConfig = request.app.state.config
        return {
            "id": config.mock_default_user_id,
            "username": config.mock_default_user_name,
            "avatar": None,
        }
    user = current_user(request)
    if user is None:
        next_url = str(request.url.path)
        if request.url.query:
            next_url += f"?{request.url.query}"
        raise _LoginRedirect(
            RedirectResponse(url=f"/auth/login?next={quote(next_url)}", status_code=302)
        )
    if _is_owner(request):
        return user
    config: AppConfig = request.app.state.config
    if not _is_guild_member(request, config.default_guild_id):
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

    Returns the session's ``guild``, or falls back to the default.
    Keeps a backward-compat read of ``active_guild_id`` for existing
    sessions that haven't re-logged since the rename.
    """
    config: AppConfig = request.app.state.config
    return (
        request.session.get("guild")
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


async def require_guild_admin(
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_login),
) -> dict[str, Any]:
    """Verify the session-user is an admin of the active guild.

    Owner (config.owner_id) is always admin of any guild (superadmin).
    For non-owners: requires MANAGE_GUILD permission OR global admin_users
    entry OR admin_roles entry for the active guild.
    In dev mock-auth mode, all users are treated as admins.
    """
    if _is_mock_auth(request):
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

    guilds = request.session.get("guilds", [])
    match = next((g for g in guilds if int(g.get("id", 0)) == guild_id), None)
    if match is None:
        raise _unauthorized()

    perms = int(match.get("permissions", 0))
    has_manage_guild = bool(perms & 0x20)

    svc = PermissionService(session, owner_id=config.owner_id)
    is_admin = await svc.is_admin(
        guild_id,
        int(user["id"]),
        [],
        has_manage_guild=has_manage_guild,
    )
    if not is_admin:
        raise _unauthorized()
    return user
