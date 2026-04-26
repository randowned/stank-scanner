"""rebuild_from_db endpoint — integration tests against in-memory SQLite.

Covers:
    * successful rebuild returns correct row count
    * rebuild populates player_totals from existing events
    * rebuild writes to the audit log
    * rebuild via the admin HTTP endpoint
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import EventType, Guild
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import player_totals as pt_repo
from stankbot.web.routes.admin import router as admin_router

# ── helpers ────────────────────────────────────────────────────────────────


async def _event(
    session: Any,
    *,
    guild_id: int = 1,
    user_id: int,
    type: EventType | str,
    delta: int = 0,
    session_id: int | None = None,
) -> None:
    await events_repo.append(
        session,
        guild_id=guild_id,
        type=type,
        delta=delta,
        user_id=user_id,
        session_id=session_id,
    )


def _build_test_app(db_session: AsyncSession) -> FastAPI:
    """Build a minimal FastAPI app with the admin router mounted and all
    dependencies overridden to use the given test session and a fixed
    admin user / guild.
    """
    from stankbot.web.tools import get_active_guild_id, get_db, require_guild_admin

    app = FastAPI()

    async def _override_db() -> AsyncSession:
        yield db_session

    async def _override_admin() -> dict:
        return {"id": "1", "username": "admin"}

    async def _override_guild_id() -> int:
        return 1

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_guild_admin] = _override_admin
    app.dependency_overrides[get_active_guild_id] = _override_guild_id

    app.include_router(admin_router)
    return app


# ── unit-level tests (direct repo call) ────────────────────────────────────


async def test_rebuild_from_db_repo_populates_totals(session: Any) -> None:
    """Directly call pt_repo.rebuild — verifies cache is populated."""
    guild = Guild(id=1, name="Test")
    session.add(guild)
    await session.flush()

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=20)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=30)
    await _event(session, user_id=200, type=EventType.PP_BREAK, delta=25)
    await session.flush()

    count = await pt_repo.rebuild(session, 1)
    assert count == 2  # two users with all-time rows

    row_a = await pt_repo.get(session, 1, 100)
    row_b = await pt_repo.get(session, 1, 200)
    assert row_a.earned_sp == 30  # 10 + 20
    assert row_b.earned_sp == 30
    assert row_b.punishments == 25


async def test_rebuild_from_db_repo_returns_zero_when_no_events(session: Any) -> None:
    """No events → rebuild inserts nothing."""
    guild = Guild(id=1, name="Test")
    session.add(guild)
    await session.flush()

    count = await pt_repo.rebuild(session, 1)
    assert count == 0


# ── HTTP endpoint tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rebuild_from_db_endpoint_success(session: Any) -> None:
    """POST /api/admin/rebuild-from-db returns 200 and row count."""
    guild = Guild(id=1, name="Test")
    session.add(guild)
    await session.flush()

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=30)
    await session.flush()

    app = _build_test_app(session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/admin/rebuild-from-db")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["success"] is True
    assert body["rows"] == 2  # two users rebuilt


@pytest.mark.asyncio
async def test_rebuild_from_db_endpoint_empty_guild(session: Any) -> None:
    """No events → endpoint returns rows=0."""
    guild = Guild(id=1, name="Test")
    session.add(guild)
    await session.flush()

    app = _build_test_app(session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/admin/rebuild-from-db")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["rows"] == 0


@pytest.mark.asyncio
async def test_rebuild_from_db_endpoint_writes_audit_log(session: Any) -> None:
    """A row is added to the audit_log table after rebuild."""
    from sqlalchemy import select

    from stankbot.db.models import AuditLog

    guild = Guild(id=1, name="Test")
    session.add(guild)
    await session.flush()
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await session.flush()

    app = _build_test_app(session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/admin/rebuild-from-db")

    # Audit log should have one entry for this action
    stmt = select(AuditLog).where(
        AuditLog.guild_id == 1, AuditLog.action == "rebuild_from_db"
    )
    rows = (await session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_id == 1


@pytest.mark.asyncio
async def test_rebuild_from_db_all_time_and_per_session(session: Any) -> None:
    """All-time (session_id=0) and per-session rows both get rebuilt."""
    guild = Guild(id=1, name="Test")
    session.add(guild)
    await session.flush()

    sid1 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id
    sid2 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=5, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=8, session_id=sid2)
    await session.flush()

    app = _build_test_app(session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/admin/rebuild-from-db")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["rows"] == 3  # 1 all-time + 2 per-session
