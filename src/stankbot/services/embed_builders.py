"""Centralised embed construction for automated bot posts.

One place to assemble the context dicts that feed `template_engine.render_embed`
for records, chain-breaks, new-session rollovers, and public cooldown notices.
Used by the chain listener, session scheduler, admin preview command, and web
API sample-preview.

Keeping stank_emoji resolution here avoids three copies of the same
`guild.emojis` scan + `altar.display_name` fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Altar, Record, RecordScope
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import players as players_repo
from stankbot.services import template_store
from stankbot.services.board_renderer import PlayerRow
from stankbot.services.template_engine import RenderContext, render_embed


def resolve_stank_emoji(
    guild: discord.Guild | None, altar: Altar | None
) -> str:
    """Return usable emoji markup for an altar.

    Derived directly from the altar's configured reaction emoji so the
    board and announcements always mirror whatever was set via
    ``/stank-admin altar set``. Falls back to ``altar.display_name`` for
    legacy rows, then the literal ``:Stank:``.
    """
    if altar is not None:
        if altar.reaction_emoji_id is not None and altar.reaction_emoji_name:
            prefix = "a" if altar.reaction_emoji_animated else ""
            return f"<{prefix}:{altar.reaction_emoji_name}:{altar.reaction_emoji_id}>"
        if altar.reaction_emoji_name:
            return altar.reaction_emoji_name
        if altar.display_name:
            return altar.display_name
    return ":Stank:"


def sticker_url(altar: Altar | None) -> str:
    if altar is None or altar.sticker_id is None:
        return ""
    return f"https://cdn.discordapp.com/stickers/{altar.sticker_id}.png"


def board_url_for(oauth_redirect_uri: str, guild_id: int) -> str:
    """Build the public board URL from the OAuth redirect.

    OAuth redirect looks like ``http://host/auth/callback`` — strip the
    last two path segments to recover the site root. The dashboard is
    single-guild now so ``/`` is the board; ``guild_id`` is kept in the
    signature for call-site compatibility.
    """
    del guild_id
    return oauth_redirect_uri.rsplit("/", 2)[0] + "/"


def altar_channel_mention(channel_id: int | None) -> str:
    return f"<#{channel_id}>" if channel_id else ""


@dataclass(slots=True)
class RecordBreakVars:
    length: int
    unique: int
    alltime_length: int
    alltime_unique: int
    session_broken: bool
    alltime_broken: bool
    starter_name: str
    starter_sp: int


async def build_record_embed(
    *,
    altar: Altar | None,
    guild: discord.Guild | None,
    vars_: RecordBreakVars,
    altar_channel: str = "",
    board_url: str = "",
    session: AsyncSession,
) -> discord.Embed:
    if vars_.alltime_broken:
        title = "\U0001f451 ALL-TIME RECORD! \U0001f451"
        color = "#ff006e"
        description = (
            f"New all-time record: **{vars_.length}** stanks "
            f"(**{vars_.unique}** unique)!"
        )
    elif vars_.session_broken:
        title = "\U0001f389 NEW SESSION RECORD! \U0001f389"
        color = "#ffd166"
        description = (
            f"Session record now **{vars_.length}** stanks "
            f"(**{vars_.unique}** unique)."
        )
    else:
        title = "Record update"
        color = "#a47cff"
        description = "No record broken."

    ctx = RenderContext(
        variables={
            "stank_emoji": resolve_stank_emoji(guild, altar),
            "altar_sticker_url": sticker_url(altar),
            "record_title": title,
            "record_color": color,
            "record_description": description,
            "record": vars_.length,
            "record_unique": vars_.unique,
            "alltime_record": vars_.alltime_length,
            "alltime_record_unique": vars_.alltime_unique,
            "session_marker": "**" if vars_.session_broken else "",
            "alltime_marker": "**" if vars_.alltime_broken else "",
            "chain_starter_name": vars_.starter_name,
            "chain_starter_sp": vars_.starter_sp,
            "altar_channel": altar_channel,
            "altar_channel_id": altar.channel_id if altar else 0,
            "altar_channel_mention": altar_channel_mention(
                altar.channel_id if altar else None
            ),
            "board_url": board_url,
        }
    )
    guild_id = guild.id if guild is not None else 0
    tmpl = await template_store.load("record_embed", session, guild_id)
    return render_embed(tmpl, ctx)


@dataclass(slots=True)
class ChainBreakVars:
    breaker_name: str
    broken_length: int
    broken_unique: int
    pp_awarded: int
    starter_name: str
    starter_sp: int
    finish_recipient_name: str
    finish_bonus_sp: int


async def build_chain_break_embed(
    *,
    altar: Altar | None,
    guild: discord.Guild | None,
    vars_: ChainBreakVars,
    altar_channel: str = "",
    board_url: str = "",
    session: AsyncSession,
) -> discord.Embed:
    ctx = RenderContext(
        variables={
            "stank_emoji": resolve_stank_emoji(guild, altar),
            "altar_sticker_url": sticker_url(altar),
            "breaker_name": vars_.breaker_name,
            "broken_length": vars_.broken_length,
            "broken_unique": vars_.broken_unique,
            "pp_awarded": vars_.pp_awarded,
            "chain_starter_name": vars_.starter_name,
            "chain_starter_sp": vars_.starter_sp,
            "finish_recipient_name": vars_.finish_recipient_name,
            "finish_bonus_sp": vars_.finish_bonus_sp,
            "altar_channel": altar_channel,
            "altar_channel_id": altar.channel_id if altar else 0,
            "altar_channel_mention": altar_channel_mention(
                altar.channel_id if altar else None
            ),
            "board_url": board_url,
        }
    )
    guild_id = guild.id if guild is not None else 0
    tmpl = await template_store.load("chain_break_embed", session, guild_id)
    return render_embed(tmpl, ctx)


async def build_cooldown_embed(
    *,
    target_display_name: str,
    cooldown_remaining: str,
    cooldown_total: str,
    altar_channel: str = "",
    altar_channel_id: int = 0,
    board_url: str = "",
    session: AsyncSession,
    guild_id: int = 0,
) -> discord.Embed:
    ctx = RenderContext(
        variables={
            "target_display_name": target_display_name,
            "cooldown_remaining": cooldown_remaining,
            "cooldown_total": cooldown_total,
            "altar_channel": altar_channel,
            "altar_channel_id": altar_channel_id,
            "altar_channel_mention": altar_channel_mention(altar_channel_id),
            "board_url": board_url,
        }
    )
    tmpl = await template_store.load("cooldown_embed", session, guild_id)
    return render_embed(tmpl, ctx)


@dataclass(slots=True)
class NewSessionVars:
    new_session_number: int
    ended_session_number: int
    chain_continuity_summary: str
    session_top_player: str
    session_top_sp: int
    session_top_breaker: str
    session_top_breaker_pp: int
    prev_session_record: int
    prev_session_record_unique: int
    alltime_record: int
    alltime_record_unique: int
    alltime_top_sp_player: str
    alltime_top_sp: int
    alltime_top_pp_player: str
    alltime_top_pp: int
    next_reset_in: str


async def build_new_session_embed(
    vars_: NewSessionVars,
    *,
    altar_channel: str = "",
    altar_channel_id: int = 0,
    board_url: str = "",
    session: AsyncSession,
    guild_id: int = 0,
) -> discord.Embed:
    ctx = RenderContext(
        variables={
            "new_session_number": vars_.new_session_number,
            "ended_session_number": vars_.ended_session_number,
            "chain_continuity_summary": vars_.chain_continuity_summary,
            "session_top_player": vars_.session_top_player,
            "session_top_sp": vars_.session_top_sp,
            "session_top_breaker": vars_.session_top_breaker,
            "session_top_breaker_pp": vars_.session_top_breaker_pp,
            "prev_session_record": vars_.prev_session_record,
            "prev_session_record_unique": vars_.prev_session_record_unique,
            "alltime_record": vars_.alltime_record,
            "alltime_record_unique": vars_.alltime_record_unique,
            "alltime_top_sp_player": vars_.alltime_top_sp_player,
            "alltime_top_sp": vars_.alltime_top_sp,
            "alltime_top_pp_player": vars_.alltime_top_pp_player,
            "alltime_top_pp": vars_.alltime_top_pp,
            "next_reset_in": vars_.next_reset_in,
            "altar_channel": altar_channel,
            "altar_channel_id": altar_channel_id,
            "altar_channel_mention": altar_channel_mention(altar_channel_id),
            "board_url": board_url,
        }
    )
    tmpl = await template_store.load("new_session_embed", session, guild_id)
    return render_embed(tmpl, ctx)


# --- data-assembly helpers ------------------------------------------------


async def display_name_of(
    session: AsyncSession, guild_id: int, user_id: int | None
) -> str:
    if user_id is None:
        return "—"
    player = await players_repo.get(session, guild_id, user_id)
    return player.display_name if player else str(user_id)


async def current_record(
    session: AsyncSession, *, guild_id: int, altar_id: int, scope: RecordScope
) -> tuple[int, int]:
    row = await session.get(Record, (guild_id, altar_id, str(scope)))
    if row is None:
        return 0, 0
    return row.chain_length, row.unique_count


async def alltime_top_sp(
    session: AsyncSession, guild_id: int
) -> tuple[str, int]:
    rows = await events_repo.leaderboard(session, guild_id, limit=1)
    if not rows:
        return "—", 0
    uid, sp, _pp = rows[0]
    name = await display_name_of(session, guild_id, uid)
    return name, int(sp)


async def alltime_top_pp(
    session: AsyncSession, guild_id: int
) -> tuple[str, int]:
    pair = await events_repo.top_pp_user(session, guild_id)
    if pair is None:
        return "—", 0
    uid, pp = pair
    name = await display_name_of(session, guild_id, uid)
    return name, int(pp)


__all__ = [
    "ChainBreakVars",
    "NewSessionVars",
    "PlayerRow",
    "RecordBreakVars",
    "altar_channel_mention",
    "alltime_top_pp",
    "alltime_top_sp",
    "board_url_for",
    "build_chain_break_embed",
    "build_cooldown_embed",
    "build_new_session_embed",
    "build_record_embed",
    "current_record",
    "display_name_of",
    "resolve_stank_emoji",
    "sticker_url",
]
