"""FastAPI app factory.

The web layer shares the same SQLAlchemy models + services as the bot.
When launched from ``__main__``, the FastAPI app runs on the same event
loop as the Discord client; the sessionmaker is passed in so every
request opens its own DB session via the ``session_scope`` helper.

Auth is Discord OAuth2 (identify + guilds). Admin routes additionally
check :func:`stankbot.services.permission_service.is_admin` against the
authenticated user's Discord roles for the requested guild.
"""

from __future__ import annotations

import logging
import os
import secrets
from importlib.metadata import version as pkg_version
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from stankbot.bot import StankBot
from stankbot.config import AppConfig
from stankbot.web import ws
from stankbot.web.routes import admin, api, auth
from stankbot.web.tools import _LoginRedirect, _NotInGuild

log = logging.getLogger(__name__)
WEB_DIR = Path(os.environ.get("WEB_DIR", str(Path(__file__).parent / "frontend")))

def build_app(
    config: AppConfig,
    engine: AsyncEngine,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    *,
    bot: StankBot | None = None,
) -> FastAPI:
    app = FastAPI(title="StankBot", docs_url=None, redoc_url=None)

    secret = (
        config.web_secret_key.get_secret_value()
        if config.web_secret_key is not None
        else secrets.token_urlsafe(32)
    )
    app.add_middleware(SessionMiddleware, secret_key=secret, same_site="lax")

    try:
        app.state.app_version = pkg_version("stankbot")
    except Exception:
        app.state.app_version = "0.0.0"

    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.bot = bot
    if bot is not None:
        app.state.bot_guilds = bot._bot_guilds
    else:
        app.state.bot_guilds = []

    app.include_router(ws.router)
    app.include_router(api.router)
    app.include_router(admin.router)
    app.include_router(auth.router)

    @app.on_event("startup")
    async def _warm_player_totals() -> None:
        """Rebuild player_totals cache from events on first boot.

        The cache is maintained write-through going forward, but on a fresh
        deploy the table may be empty while events exist. A one-time scan at
        startup avoids a costly lazy rebuild on the first leaderboard query.
        """
        from sqlalchemy import func, select

        from stankbot.db.models import Guild, PlayerTotal
        from stankbot.db.repositories import player_totals as pt_repo

        async with session_factory() as s:
            guild_ids = list(
                (await s.execute(select(Guild.id))).scalars().all()
            )
            for gid in guild_ids:
                cached = await s.execute(
                    select(func.count()).where(PlayerTotal.guild_id == gid)
                )
                if cached.scalar_one() == 0:
                    count = await pt_repo.rebuild(s, gid)
                    if count:
                        log.info("Warmed player_totals for guild %d: %d rows", gid, count)
            await s.commit()

    @app.get("/healthz", include_in_schema=False)
    async def _healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/version", include_in_schema=False)
    async def _version() -> JSONResponse:
        return JSONResponse({"version": app.state.app_version})

    if config.env == "dev-mock":
        from stankbot.web.routes import mock_events

        app.include_router(mock_events.router)
        log.info("Mock event API mounted at /api/mock")

    @app.exception_handler(_LoginRedirect)
    async def _login_redirect_handler(_: Request, exc: _LoginRedirect):
        return exc.response

    @app.exception_handler(_NotInGuild)
    async def _not_in_guild_handler(_: Request, exc: _NotInGuild):
        return exc.response

    build_dir = WEB_DIR / "build"
    if build_dir.is_dir():
        spa_index = build_dir / "index.html"
        if spa_index.is_file():
            @app.get("/{path:path}")
            async def spa_fallback(path: str) -> FileResponse:
                file_path = build_dir / path
                if file_path.is_file():
                    return FileResponse(file_path)
                return FileResponse(spa_index)

    return app
