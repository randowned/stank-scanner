"""Shared FastAPI dependencies — DB sessions, Jinja templates, auth."""

from __future__ import annotations

import logging
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
from stankbot.db.models import Guild, GuildMember, Player

if TYPE_CHECKING:
    from stankbot.config import AppConfig

log = logging.getLogger(__name__)


async def fetch_guild_member(
    config: AppConfig, guild_id: int, user_id: int, session: AsyncSession | None = None
) -> dict[str, Any] | None:
    """Check if user is a member of guild — DB-first, Discord API fallback.

    Queries ``guild_member_roles`` (populated on first interaction and kept
    fresh by ``on_member_update`` events). On miss, calls Discord
    ``GET /guilds/{guild_id}/members/{user_id}`` and stores the result.

    Returns a member dict with ``roles``, ``permissions``, ``nick``, and a
    ``user`` sub-object, or ``None`` if the member is not found.
    """
    if session is not None:
        row = await session.get(GuildMember, (guild_id, user_id))
        if row is not None:
            return {
                "roles": row.role_ids or [],
                "permissions": str(row.permissions),
                "nick": row.nick,
                "user": {
                    "id": str(user_id),
                    "username": row.username or str(user_id),
                    "avatar": row.avatar,
                    "global_name": row.global_name,
                },
            }

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
            return None
        if resp.status_code != 200:
            log.warning(
                "fetch_guild_member failed: guild=%d user=%d status=%d",
                guild_id,
                user_id,
                resp.status_code,
            )
            return None

        data: dict[str, Any] = resp.json()

        if session is not None:
            user_obj: dict[str, Any] = data.get("user", {})
            await session.merge(
                GuildMember(
                    guild_id=guild_id,
                    user_id=user_id,
                    role_ids=[int(r) for r in data.get("roles", [])],
                    permissions=int(data.get("permissions", 0)),
                    nick=data.get("nick"),
                    username=user_obj.get("username") or str(user_id),
                    global_name=user_obj.get("global_name"),
                    avatar=user_obj.get("avatar"),
                )
            )

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


async def _is_guild_member(
    request: Request, guild_id: int, user_id: int, session: AsyncSession | None = None
) -> bool:
    """Return True if the user is a member of the given guild (DB-first, Discord fallback)."""
    config: AppConfig = request.app.state.config
    member = await fetch_guild_member(config, guild_id, user_id, session=session)
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


async def require_guild_member(
    request: Request, session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
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
    is_member = await _is_guild_member(request, default_gid, uid, session=session)
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
    """Return ``{user_id: display_name}`` preferring guild_members, falling back to players."""
    ids = [int(u) for u in user_ids if u is not None]
    if not ids:
        return {}
    result: dict[int, str] = {}
    gm_rows = (
        await session.execute(
            select(GuildMember.user_id, GuildMember.nick, GuildMember.global_name, GuildMember.username).where(
                GuildMember.guild_id == guild_id, GuildMember.user_id.in_(ids)
            )
        )
    ).all()
    for uid, nick, gname, uname in gm_rows:
        name = nick or gname or uname
        if name:
            result[int(uid)] = name
    missing = [uid for uid in ids if uid not in result]
    if missing:
        p_rows = (
            await session.execute(
                select(Player.user_id, Player.display_name).where(
                    Player.guild_id == guild_id, Player.user_id.in_(missing)
                )
            )
        ).all()
        for uid, name in p_rows:
            result[int(uid)] = name or str(uid)
    return {uid: result.get(uid) or str(uid) for uid in ids}


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
    Discord Manage Guild permission is also accepted.
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

    member = await fetch_guild_member(config, guild_id, uid, session=session)
    if member is None:
        raise _unauthorized()

    if await svc.is_guild_admin(guild_id, uid, user_role_ids=member.get("roles", [])):
        return user

    perms = int(member.get("permissions", 0))
    has_manage_guild = bool(perms & 0x20)
    if has_manage_guild:
        return user

    raise _unauthorized()
