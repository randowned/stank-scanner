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
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from stankbot.bot import StankBot
from stankbot.config import AppConfig
from stankbot.web import v2_app
from stankbot.web.deps import _LoginRedirect, _NotInGuild
from stankbot.web.routes import admin, auth, history, player, public

log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_WEB_DIR = Path(os.environ.get("V2_WEB_DIR", str(Path(__file__).parent.parent.parent.parent / "web")))


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

    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.templates_dir = _TEMPLATES_DIR
    app.state.bot = bot
    if bot is not None:
        app.state.bot_guilds = bot._bot_guilds
    else:
        app.state.bot_guilds = []

    static_dir = _TEMPLATES_DIR.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    v2_build_dir = _WEB_DIR / "build"
    if v2_build_dir.is_dir():
        app.mount("/v2", StaticFiles(directory=str(v2_build_dir), html=True), name="v2_static")

    app.include_router(v2_app._API_ROUTER)

    @app.exception_handler(_LoginRedirect)
    async def _login_redirect_handler(_: Request, exc: _LoginRedirect):
        return exc.response

    @app.exception_handler(_NotInGuild)
    async def _not_in_guild_handler(_: Request, exc: _NotInGuild):
        return exc.response

    @app.get("/healthz", include_in_schema=False)
    async def _healthz() -> JSONResponse:
        # Liveness probe for Railway/containers. Returning 200 as soon as
        # the web server is up is sufficient — Discord gateway connection
        # is async and may not be ready at first hit, but the process is
        # alive and that's what the platform needs to know to route
        # traffic to this container.
        return JSONResponse({"status": "ok"})

    app.include_router(auth.router)
    app.include_router(public.router)
    app.include_router(player.router)
    app.include_router(history.router)
    app.include_router(admin.router)

    return app
