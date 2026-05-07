"""Player repository — identity + last-seen tracking.

Thin module, not a heavyweight class. Callers pass an ``AsyncSession``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import GuildMember, Player


async def get_or_create(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    display_name: str | None = None,
    discord_avatar: str | None = None,
) -> Player:
    player = await session.get(Player, (guild_id, user_id))
    if player is None:
        player = Player(
            guild_id=guild_id,
            user_id=user_id,
            display_name=display_name or str(user_id),
            discord_avatar=discord_avatar,
        )
        session.add(player)
        await session.flush()
    else:
        if display_name and display_name != player.display_name:
            player.display_name = display_name
        elif not player.display_name:
            player.display_name = str(user_id)
        if discord_avatar and discord_avatar != player.discord_avatar:
            player.discord_avatar = discord_avatar
    return player


async def get(session: AsyncSession, guild_id: int, user_id: int) -> Player | None:
    """Read-only fetch that guarantees a non-None ``display_name``.

    If the row exists with a missing name, the in-memory attribute is
    filled with ``str(user_id)`` so callers never have to re-apply the
    fallback themselves.
    """
    player = await session.get(Player, (guild_id, user_id))
    if player is not None and not player.display_name:
        player.display_name = str(user_id)
    return player


async def display_names(
    session: AsyncSession, guild_id: int, user_ids: Iterable[int]
) -> dict[int, str]:
    """Return ``{user_id: display_name}`` preferring guild_members, falling back to players."""
    ids = [int(u) for u in user_ids if u is not None]
    if not ids:
        return {}

    gm_rows = (
        await session.execute(
            select(GuildMember.user_id, GuildMember.nick, GuildMember.global_name, GuildMember.username).where(
                GuildMember.guild_id == guild_id, GuildMember.user_id.in_(ids)
            )
        )
    ).all()
    gm_names = {
        int(uid): nick or gname or uname
        for uid, nick, gname, uname in gm_rows
        if nick or gname or uname
    }

    missing = [uid for uid in ids if uid not in gm_names]
    if missing:
        p_rows = (
            await session.execute(
                select(Player.user_id, Player.display_name).where(
                    Player.guild_id == guild_id, Player.user_id.in_(missing)
                )
            )
        ).all()
        for uid, name in p_rows:
            gm_names[int(uid)] = name or str(uid)

    result: dict[int, str] = {}
    for uid in ids:
        uid_int = int(uid)
        result[uid_int] = gm_names.get(uid_int) or str(uid_int)
    return result


async def display_names_and_avatars(
    session: AsyncSession, guild_id: int, user_ids: Iterable[int]
) -> dict[int, tuple[str, str | None]]:
    """Return ``{user_id: (display_name, avatar_hash)}`` preferring guild_members, falling back to players."""
    ids = [int(u) for u in user_ids if u is not None]
    if not ids:
        return {}

    gm_rows = (
        await session.execute(
            select(
                GuildMember.user_id,
                GuildMember.nick,
                GuildMember.global_name,
                GuildMember.username,
                GuildMember.avatar,
            ).where(
                GuildMember.guild_id == guild_id, GuildMember.user_id.in_(ids)
            )
        )
    ).all()
    gm_map: dict[int, tuple[str, str | None]] = {}
    for uid, nick, gname, uname, av in gm_rows:
        name = nick or gname or uname
        if name:
            gm_map[int(uid)] = (name, av)

    missing = [uid for uid in ids if uid not in gm_map]
    if missing:
        p_rows = (
            await session.execute(
                select(Player.user_id, Player.display_name, Player.discord_avatar).where(
                    Player.guild_id == guild_id, Player.user_id.in_(missing)
                )
            )
        ).all()
        for uid, name, av in p_rows:
            gm_map[int(uid)] = (name or str(uid), av)

    result: dict[int, tuple[str, str | None]] = {}
    for uid in ids:
        uid_int = int(uid)
        result[uid_int] = gm_map.get(uid_int) or (str(uid_int), None)
    return result


async def touch_last_seen(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    *,
    when: datetime | None = None,
) -> None:
    player = await session.get(Player, (guild_id, user_id))
    if player is None:
        return
    player.last_seen_at = when or datetime.now(tz=UTC)
