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
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from stankbot.bot import StankBot
from stankbot.config import AppConfig
from stankbot.web import ws
from stankbot.web.routes import admin, api, auth, media_admin, media_api
from stankbot.web.tools import _LoginRedirect, _NotInGuild

log = logging.getLogger(__name__)
WEB_DIR = Path(os.environ.get("WEB_DIR", str(Path(__file__).parent / "frontend")))


class _SPAStaticFiles(StaticFiles):
    """Serve index.html for any unmatched path (SPA fallback)."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("", scope)
            raise

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
    app.include_router(media_api.router)
    app.include_router(media_admin.router)

    # Share the media registry from the bot (if available).
    # In dev-mock mode, always use mock providers regardless.
    if config.env == "dev-mock":
        from stankbot.services.media_providers import MediaProviderRegistry
        from stankbot.services.media_providers.mock_providers import (
            MockSpotifyProvider,
            MockYouTubeProvider,
        )

        registry = MediaProviderRegistry()
        registry.register(MockYouTubeProvider())
        registry.register(MockSpotifyProvider())
        app.state.media_registry = registry
        log.info("Mock media providers registered (dev-mock)")
    elif bot is not None and hasattr(bot, "media_registry"):
        app.state.media_registry = bot.media_registry
    else:
        from stankbot.services.media_providers import MediaProviderRegistry

        app.state.media_registry = MediaProviderRegistry()

    @app.get("/healthz", include_in_schema=False)
    async def _healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/version", include_in_schema=False)
    async def _version() -> JSONResponse:
        return JSONResponse({"version": app.state.app_version})

    if config.env == "dev-mock":
        from stankbot.web.routes import mock_events, mock_media

        app.include_router(mock_events.router)
        app.include_router(mock_media.router)
        log.info("Mock event API mounted at /api/mock")

    @app.exception_handler(_LoginRedirect)
    async def _login_redirect_handler(_: Request, exc: _LoginRedirect):
        return exc.response

    @app.exception_handler(_NotInGuild)
    async def _not_in_guild_handler(_: Request, exc: _NotInGuild):
        return exc.response

    build_dir = WEB_DIR / "build"
    if build_dir.is_dir() and (build_dir / "index.html").is_file():
        app.mount("/", _SPAStaticFiles(directory=str(build_dir), html=True), name="static")

    return app
