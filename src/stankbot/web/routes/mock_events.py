"""Mock event API — only mounted when ENV=dev.

These endpoints allow manual and automated injection of fake stanks,
breaks, and reactions for local development and Playwright E2E tests.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from stankbot.db.engine import session_scope
from stankbot.db.models import SessionEndReason
from stankbot.services.session_service import SessionService
from stankbot.web.tools import get_config

router = APIRouter(prefix="/api/mock", tags=["mock"])
log = logging.getLogger(__name__)


def _dev_only(request: Request) -> None:
    config = request.app.state.config
    if config.env != "dev":
        raise HTTPException(status_code=403, detail="Mock endpoints only available in dev mode")


def _get_bridge(request: Request):
    """Lazy-initialize the MockEventBridge on first use."""
    bridge = getattr(request.app.state, "_mock_event_bridge", None)
    if bridge is None:
        from stankbot.services.mock_event_bridge import MockEventBridge

        bridge = MockEventBridge(
            request.app.state.session_factory,
            request.app.state.config,
        )
        request.app.state._mock_event_bridge = bridge
    return bridge


def _get_generator(request: Request):
    """Lazy-initialize the MockEventGenerator on first use."""
    gen = getattr(request.app.state, "_mock_event_generator", None)
    if gen is None:
        from stankbot.services.mock_event_generator import MockEventGenerator

        config = request.app.state.config
        guild_id = config.mock_default_guild_id or config.default_guild_id
        bridge = _get_bridge(request)
        gen = MockEventGenerator(bridge, guild_id, interval=config.mock_auto_events_interval)
        request.app.state._mock_event_generator = gen
    return gen


@router.post("/stank")
async def mock_stank(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)
    user_id = body.get("user_id", 1001)
    display_name = body.get("display_name", "Alice")

    bridge = _get_bridge(request)
    await bridge.ensure_guild(guild_id)
    result = await bridge.inject_stank(guild_id, user_id, display_name)
    return JSONResponse(result)


@router.post("/break")
async def mock_break(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)
    user_id = body.get("user_id", 1001)
    display_name = body.get("display_name", "Alice")

    bridge = _get_bridge(request)
    await bridge.ensure_guild(guild_id)
    result = await bridge.inject_break(guild_id, user_id, display_name)
    return JSONResponse(result)


@router.post("/reaction")
async def mock_reaction(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)
    message_id = body.get("message_id", 10_000_001)
    user_id = body.get("user_id", 1001)
    sticker_id = body.get("sticker_id", 1)

    bridge = _get_bridge(request)
    await bridge.ensure_guild(guild_id)
    result = await bridge.inject_reaction(guild_id, message_id, user_id, sticker_id)
    return JSONResponse(result)


@router.post("/noise")
async def mock_noise(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)
    user_id = body.get("user_id", 1001)
    display_name = body.get("display_name", "Alice")

    bridge = _get_bridge(request)
    await bridge.ensure_guild(guild_id)
    result = await bridge.inject_noise(guild_id, user_id, display_name)
    return JSONResponse(result)


@router.post("/session/start")
async def mock_session_start(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)

    async with session_scope(request.app.state.session_factory) as session:
        svc = SessionService(session)
        session_id = await svc.start(guild_id)
    return JSONResponse({"session_id": session_id})


@router.post("/session/end")
async def mock_session_end(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)

    async with session_scope(request.app.state.session_factory) as session:
        svc = SessionService(session)
        ended_id, new_id = await svc.end_session(guild_id, reason=SessionEndReason.MANUAL)
    return JSONResponse({"ended_session_id": ended_id, "new_session_id": new_id})


@router.post("/random/start")
async def mock_random_start(
    request: Request,
    config=Depends(get_config),
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    interval = body.get("interval", config.mock_auto_events_interval)
    guild_id = body.get("guild_id", config.mock_default_guild_id or config.default_guild_id)

    gen = _get_generator(request)
    gen.guild_id = guild_id
    gen.interval = interval
    await gen.start()
    return JSONResponse({"status": "started", "interval": interval, "guild_id": guild_id})


@router.post("/random/stop")
async def mock_random_stop(
    request: Request,
) -> JSONResponse:
    _dev_only(request)
    gen = _get_generator(request)
    await gen.stop()
    return JSONResponse({"status": "stopped"})


@router.post("/bot-guilds")
async def mock_set_bot_guilds(
    request: Request,
) -> JSONResponse:
    _dev_only(request)
    body = await request.json()
    request.app.state.bot_guilds = body.get("guilds", [])
    return JSONResponse({"ok": True})


@router.get("/state")
async def mock_state(
    request: Request,
) -> JSONResponse:
    _dev_only(request)
    gen = getattr(request.app.state, "_mock_event_generator", None)
    running = gen is not None and gen._task is not None and not gen._task.done()
    return JSONResponse({
        "running": running,
        "interval": getattr(gen, "interval", None) if gen else None,
        "guild_id": getattr(gen, "guild_id", None) if gen else None,
    })
