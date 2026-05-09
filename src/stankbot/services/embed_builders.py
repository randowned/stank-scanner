"""Centralised embed construction for automated bot posts.

One place to assemble the context dicts that feed `template_engine.render_embed`
for records, chain-breaks, new-session rollovers, public cooldown notices, and
media item displays.

Keeping stank_emoji resolution here avoids three copies of the same
`guild.emojis` scan + `altar.display_name` fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import discord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Altar, MetricSnapshot, Record, RecordScope
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import media as media_repo
from stankbot.db.repositories import players as players_repo
from stankbot.services import template_store
from stankbot.services.board_renderer import PlayerRow
from stankbot.services.media_service import MilestoneInfo, next_milestone, prev_milestone
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


async def build_media_embed(
    *,
    media_type: str,
    media_item_id: int,
    title: str,
    channel_name: str | None,
    name: str | None,
    thumbnail_url: str | None,
    published_at: str | None,
    duration_seconds: int | None,
    metrics: dict[str, str | int],
    last_fetched_at: str | None,
    guild_id: int,
    session: AsyncSession,
    base_url: str = "",
) -> discord.Embed:
    """Build a media item embed from the guild's per-provider template.

    Variables available in templates:
        {title}, {channel_name}, {name}, {url}, {image_url},
        {published_at}, {duration}, {last_fetched_at},
        {view_count}, {view_count_delta},
        {like_count}, {like_count_delta},
        {comment_count}, {comment_count_delta},
        {popularity}, {popularity_delta}, {spotify_type} -> {playcount}, {playcount_delta}, {spotify_type}

    {slug} is a legacy alias for {name} (preserved for user-customized templates).
    """

    def _fmt_num(n: int) -> str:
        """Format integer with thousand separators: 12,345,678."""
        return f"{n:,}"

    def _fmt_duration(secs: int | None) -> str:
        if not secs:
            return "—"
        h, m = divmod(secs, 3600)
        m, s = divmod(m, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def _fmt_date(iso: str | None) -> str:
        if not iso:
            return "—"
        try:
            dt = datetime.fromisoformat(iso)
            return dt.strftime("%b %d, %Y")
        except (ValueError, TypeError):
            return iso[:10]

    def _fmt_relative(iso: str | None) -> str:
        if not iso:
            return "\u2014"
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            diff = datetime.now(UTC) - dt
            secs = diff.total_seconds()
            if secs < 60:
                return "just now"
            mins = int(secs // 60)
            if mins < 2:
                return "1 minute ago"
            if mins < 60:
                return f"{mins} minutes ago"
            hrs = mins // 60
            if hrs < 2:
                return "1 hour ago"
            if hrs < 24:
                return f"{hrs} hours ago"
            days = diff.days
            if days < 2:
                return "1 day ago"
            if days < 14:
                return f"{days} days ago"
            weeks = days // 7
            if weeks < 5:
                return f"{weeks} weeks ago"
            months = days // 30
            if months < 12:
                return f"{months} months ago"
            return f"{days // 365} years ago"
        except (ValueError, TypeError):
            return "\u2014"

    # Day-over-day deltas
    yesterday = datetime.now(UTC) - timedelta(hours=24)

    async def _delta(metric_key: str, current: int) -> str:
        if current == 0:
            return ""
        snaps = await media_repo.get_metric_snapshots(
            session, media_item_id, metric_key, since=yesterday
        )
        if len(snaps) < 2:
            return ""
        baseline = snaps[0].value
        diff = current - baseline
        if diff == 0:
            return "(no change)"
        sign = "+" if diff > 0 else ""
        return f"({sign}{_fmt_num(diff)} since yesterday)"

    view_count = int(metrics.get("view_count", 0))
    like_count = int(metrics.get("like_count", 0))
    comment_count = int(metrics.get("comment_count", 0))
    playcount = int(metrics.get("playcount", 0))

    if not last_fetched_at:
        latest = await session.execute(
            select(MetricSnapshot.fetched_at)
            .where(MetricSnapshot.media_item_id == media_item_id)
            .order_by(MetricSnapshot.fetched_at.desc())
            .limit(1)
        )
        row = latest.scalar()
        if row:
            last_fetched_at = row.isoformat()

    variables: dict[str, Any] = {
        "title": title or "",
        "channel_name": channel_name or "",
        "name": name or "",
        "slug": name or "",  # legacy alias
        "image_url": thumbnail_url or "",
        "published_at": _fmt_date(published_at),
        "duration": _fmt_duration(duration_seconds),
        "last_fetched_at": _fmt_relative(last_fetched_at),
    }

    if media_type == "youtube":
        variables["provider_url"] = f"https://youtube.com/watch?v={metrics.get('external_id', '')}"
        variables["url"] = f"{base_url}/media/{media_item_id}" if base_url else variables["provider_url"]
        variables["view_count"] = _fmt_num(view_count)
        variables["like_count"] = _fmt_num(like_count)
        variables["comment_count"] = _fmt_num(comment_count)
        variables["view_count_delta"] = await _delta("view_count", view_count)
        variables["like_count_delta"] = await _delta("like_count", like_count)
        variables["comment_count_delta"] = await _delta("comment_count", comment_count)
        variables["milestone_progress"] = _milestone_progress_bar(view_count, next_milestone(view_count), prev_milestone(view_count))
        template_key = "youtube_media_embed"
    else:
        variables["provider_url"] = "https://open.spotify.com/" + media_type + "/" + str(metrics.get('external_id', ''))
        variables["url"] = f"{base_url}/media/{media_item_id}" if base_url else variables["provider_url"]
        variables["playcount"] = _fmt_num(playcount)
        variables["spotify_type"] = media_type
        variables["playcount_delta"] = await _delta("playcount", playcount)
        variables["milestone_progress"] = _milestone_progress_bar(playcount, next_milestone(playcount), prev_milestone(playcount))
        template_key = "spotify_media_embed"

    ctx = RenderContext(variables=variables)
    tmpl = await template_store.load(template_key, session, guild_id)
    return render_embed(tmpl, ctx)


def _fmt_compact(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B".replace(".0B", "B")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(n)


def _milestone_progress_bar(current: int, target: int | None, previous: int = 0, bar_length: int = 10) -> str:
    if target is None or target <= 0:
        return "No milestones remaining"
    if current >= target:
        return f"100% to {_fmt_compact(target)}"
    segment = target - previous
    offset = current - previous
    pct = offset / segment
    filled = int(bar_length * pct)
    empty = bar_length - filled
    pct_str = f"{int(pct * 100)}%"
    if filled == 0:
        bar = "\u2591" * bar_length
    elif empty == 0:
        bar = "\u2588" * bar_length
    else:
        bar = "\u2588" * filled + "\u2591" * empty
    return f"{bar} {pct_str} to {_fmt_compact(target)}"


async def build_media_milestone_embed(
    *,
    info: MilestoneInfo,
    other_metrics: str,
    chart_url: str,
    guild_id: int,
    session: AsyncSession,
    base_url: str = "",
) -> discord.Embed:
    def _fmt_num(n: int) -> str:
        return f"{n:,}"

    metric_label = "Views" if info.metric_key == "view_count" else "Play Count"

    if info.media_type == "youtube":
        provider_url = f"https://youtube.com/watch?v={info.external_id}"
        template_key = "youtube_milestone_embed"
    else:
        provider_url = f"https://open.spotify.com/{info.media_type}/{info.external_id}"
        template_key = "spotify_milestone_embed"

    media_page_url = f"{base_url}/media/{info.media_item_id}" if base_url else provider_url
    board_url = base_url if base_url else ""

    ctx = RenderContext(
        variables={
            "title": info.title,
            "provider_url": provider_url,
            "thumbnail_url": info.thumbnail_url or "",
            "chart_url": chart_url,
            "milestone_value": _fmt_num(info.milestone_value),
            "metric_label": metric_label,
            "other_metrics": other_metrics,
            "board_url": board_url,
            "media_page_url": media_page_url,
        }
    )
    tmpl = await template_store.load(template_key, session, guild_id)
    return render_embed(tmpl, ctx)


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
    "build_media_embed",
    "build_media_milestone_embed",
    "build_new_session_embed",
    "build_record_embed",
    "current_record",
    "display_name_of",
    "resolve_stank_emoji",
    "sticker_url",
]
