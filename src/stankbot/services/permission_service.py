"""Admin permission check — same rules for slash commands and the web.

Admin if any of:
    * the member is the global bot owner (``AppConfig.owner_id``), OR
    * the member has the Discord ``Manage Guild`` permission, OR
    * the member is listed in ``admin_users`` (global — works for all guilds), OR
    * the member has any role listed in ``admin_roles`` for this guild.

``admin_users`` is a global list (guild_id=0 sentinel rows). Adding a user
there grants them admin in every guild. ``admin_roles`` stays per-guild.

Framework-agnostic — takes plain inputs (ids, role ids, a ``has_manage_guild``
flag) so the same function serves both the discord.py layer and FastAPI.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import AdminRole, AdminUser


@dataclass(slots=True)
class PermissionService:
    session: AsyncSession
    owner_id: int | None = None

    async def is_admin(
        self,
        guild_id: int,
        user_id: int,
        user_role_ids: Iterable[int],
        *,
        has_manage_guild: bool,
    ) -> bool:
        """Legacy admin check for Discord bot commands.

        Checks: owner, MANAGE_GUILD permission, global admin_users, or guild admin_roles.
        """
        if self.owner_id is not None and user_id == self.owner_id:
            return True
        if has_manage_guild:
            return True
        global_admin_stmt = select(AdminUser.user_id).where(AdminUser.user_id == user_id)
        is_global_admin = await self.session.execute(global_admin_stmt)
        if is_global_admin.scalar_one_or_none() is not None:
            return True
        role_set = set(user_role_ids)
        if not role_set:
            return False
        stmt = select(AdminRole.role_id).where(AdminRole.guild_id == guild_id)
        admin_ids = set((await self.session.execute(stmt)).scalars().all())
        return bool(admin_ids & role_set)

    async def is_global_admin(self, user_id: int) -> bool:
        """Check if user is a global admin (owner or in admin_users table).

        Global admins can access all guilds.
        """
        if self.owner_id is not None and user_id == self.owner_id:
            return True
        stmt = select(AdminUser.user_id).where(AdminUser.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def is_guild_admin(
        self,
        guild_id: int,
        user_id: int,
        user_role_ids: Iterable[int] | None = None,
    ) -> bool:
        """Check if user is a guild admin via admin_roles table.

        Requires ``user_role_ids`` (the user's current Discord role IDs).
        Intersects with the guild's ``admin_roles`` entries.

        Returns ``False`` if ``user_role_ids`` is ``None`` (web callers
        must provide role IDs from ``guild_member_roles`` or Discord API).
        """
        if user_role_ids is None:
            return False
        role_set = set(user_role_ids)
        if not role_set:
            return False
        stmt = select(AdminRole.role_id).where(AdminRole.guild_id == guild_id)
        admin_ids = set((await self.session.execute(stmt)).scalars().all())
        return bool(admin_ids & role_set)

    async def add_admin_user(self, user_id: int) -> bool:
        stmt = select(AdminUser).where(AdminUser.guild_id == 0, AdminUser.user_id == user_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return False
        self.session.add(AdminUser(guild_id=0, user_id=user_id))
        return True

    async def remove_admin_user(self, user_id: int) -> bool:
        stmt = select(AdminUser).where(AdminUser.guild_id == 0, AdminUser.user_id == user_id)
        existing = (await self.session.execute(stmt)).scalars().all()
        if not existing:
            return False
        for row in existing:
            await self.session.delete(row)
        return True

    async def list_admin_users(self) -> list[int]:
        stmt = select(AdminUser.user_id).where(AdminUser.guild_id == 0)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_admin_role(self, guild_id: int, role_id: int) -> bool:
        """Return True if the role was added, False if it was already set."""
        existing = await self.session.get(AdminRole, (guild_id, role_id))
        if existing is not None:
            return False
        self.session.add(AdminRole(guild_id=guild_id, role_id=role_id))
        return True

    async def remove_admin_role(self, guild_id: int, role_id: int) -> bool:
        existing = await self.session.get(AdminRole, (guild_id, role_id))
        if existing is None:
            return False
        await self.session.delete(existing)
        return True

    async def list_admin_roles(self, guild_id: int) -> list[int]:
        stmt = select(AdminRole.role_id).where(AdminRole.guild_id == guild_id)
        return list((await self.session.execute(stmt)).scalars().all())
