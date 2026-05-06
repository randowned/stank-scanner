"""Unit tests for media admin settings endpoint — scheduler resync on
providers_enabled change."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.web.routes.media_admin import router as media_admin_router


def _build_test_app(
    db_session: AsyncSession,
    *,
    bot: object | None = None,
) -> FastAPI:
    from stankbot.web.tools import get_active_guild_id, get_db, require_guild_admin

    app = FastAPI()

    async def _override_db() -> Any:
        yield db_session

    async def _override_admin() -> dict[str, str]:
        return {"id": "1", "username": "admin"}

    async def _override_guild_id() -> int:
        return 7

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_guild_admin] = _override_admin
    app.dependency_overrides[get_active_guild_id] = _override_guild_id

    if bot is not None:
        app.state.bot = bot

    app.include_router(media_admin_router)
    return app


@pytest.mark.asyncio
async def test_save_providers_enabled_triggers_scheduler_sync(session: Any) -> None:
    mock_sync = AsyncMock()
    mock_scheduler = Mock()
    mock_scheduler.sync_guild = mock_sync
    mock_bot = Mock()
    mock_bot.media_scheduler = mock_scheduler

    app = _build_test_app(session, bot=mock_bot)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/media/settings",
            headers={"Content-Type": "application/msgpack"},
            content=__import__("msgpack").packb({"providers_enabled": ["youtube"]}),
        )
    assert resp.status_code == status.HTTP_200_OK
    mock_sync.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_save_providers_enabled_no_bot_no_crash(session: Any) -> None:
    app = _build_test_app(session, bot=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/media/settings",
            headers={"Content-Type": "application/msgpack"},
            content=__import__("msgpack").packb({"providers_enabled": ["spotify"]}),
        )
    assert resp.status_code == status.HTTP_200_OK
