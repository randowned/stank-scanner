"""Guild member repository — upsert identity + role cache for the
``guild_members`` table, called from cogs that have a ``discord.Member``
object in hand.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import GuildMember


async def upsert_from_member(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    *,
    role_ids: list[int] | None = None,
    permissions: int = 0,
    nick: str | None = None,
    username: str | None = None,
    global_name: str | None = None,
    avatar: str | None = None,
) -> GuildMember:
    gm = await session.get(GuildMember, (guild_id, user_id))
    if gm is None:
        gm = GuildMember(
            guild_id=guild_id,
            user_id=user_id,
            role_ids=role_ids or [],
            permissions=permissions,
            nick=nick,
            username=username,
            global_name=global_name,
            avatar=avatar,
        )
        session.add(gm)
    else:
        if role_ids is not None:
            gm.role_ids = role_ids
        if permissions:
            gm.permissions = permissions
        if nick is not None:
            gm.nick = nick
        if username is not None:
            gm.username = username
        if global_name is not None:
            gm.global_name = global_name
        if avatar is not None:
            gm.avatar = avatar
        gm.updated_at = datetime.now(tz=UTC)
    await session.flush()
    return gm
