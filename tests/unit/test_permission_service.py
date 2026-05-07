"""PermissionService.is_guild_admin tests."""

from __future__ import annotations

import pytest

from stankbot.db.models import AdminRole, Guild
from stankbot.services.permission_service import PermissionService


@pytest.fixture
async def guild(session):
    g = Guild(id=1, name="Test Guild")
    session.add(g)
    await session.flush()
    return g


async def test_is_guild_admin_role_match(session, guild):
    session.add(AdminRole(guild_id=1, role_id=100))
    session.add(AdminRole(guild_id=1, role_id=200))
    await session.flush()

    svc = PermissionService(session)
    result = await svc.is_guild_admin(1, 12345, user_role_ids=[50, 100, 150])
    assert result is True


async def test_is_guild_admin_role_no_match(session, guild):
    session.add(AdminRole(guild_id=1, role_id=100))
    await session.flush()

    svc = PermissionService(session)
    result = await svc.is_guild_admin(1, 12345, user_role_ids=[50, 150, 200])
    assert result is False


async def test_is_guild_admin_no_role_ids(session, guild):
    session.add(AdminRole(guild_id=1, role_id=100))
    await session.flush()

    svc = PermissionService(session)
    result = await svc.is_guild_admin(1, 12345, user_role_ids=None)
    assert result is False


async def test_is_guild_admin_empty_roles(session, guild):
    session.add(AdminRole(guild_id=1, role_id=100))
    await session.flush()

    svc = PermissionService(session)
    result = await svc.is_guild_admin(1, 12345, user_role_ids=[])
    assert result is False


async def test_is_guild_admin_no_admin_roles_configured(session, guild):
    svc = PermissionService(session)
    result = await svc.is_guild_admin(1, 12345, user_role_ids=[100, 200])
    assert result is False
