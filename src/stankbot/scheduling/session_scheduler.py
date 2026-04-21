"""Session scheduler — per-guild APScheduler jobs for session rollovers.

One ``CronTrigger`` per (guild, reset_hour). Plus optional warning jobs
at ``reset_warning_minutes`` before each reset (T-30, T-5 by default).

Job callbacks:
    * ``_fire_rollover`` — ends the current session, opens a new one,
      emits one unified ``new_session`` announcement.
    * ``_fire_warning`` — posts "session ending in Xm" into announcement
      channels.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from stankbot.db.models import Guild, RecordScope, SessionEndReason
from stankbot.services import embed_builders, history_service
from stankbot.services.announcement_service import broadcast_to_guild
from stankbot.services.session_service import SessionService
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.utils.time_utils import humanize_duration, next_reset_at

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)


class SessionScheduler:
    """Owns the APScheduler instance + (re)registers per-guild jobs."""

    def __init__(self, bot: StankBot) -> None:
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=UTC)

    # ---- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        await self.sync_all_guilds()
        self.scheduler.start()
        log.info("SessionScheduler started")

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # ---- registration ----------------------------------------------------

    async def sync_all_guilds(self) -> None:
        async with self.bot.db() as session:
            guilds = list((await session.execute(select(Guild.id))).scalars())
        for gid in guilds:
            await self.sync_guild(gid)

    async def sync_guild(self, guild_id: int) -> None:
        self._clear_guild_jobs(guild_id)
        async with self.bot.db() as session:
            settings = SettingsService(session)
            hours: list[int] = list(
                await settings.get(guild_id, Keys.RESET_HOURS_UTC, [7, 15, 23])
            )
            warnings: list[int] = list(
                await settings.get(guild_id, Keys.RESET_WARNING_MINUTES, [30, 5])
            )

        for hour in hours:
            self.scheduler.add_job(
                self._fire_rollover,
                CronTrigger(hour=hour, minute=0, timezone=UTC),
                args=[guild_id, hour],
                id=_rollover_job_id(guild_id, hour),
                replace_existing=True,
                misfire_grace_time=120,
            )
            for warn_minutes in warnings:
                trigger_hour = (hour - 1) % 24 if warn_minutes >= 60 else hour
                trigger_minute = (60 - warn_minutes) % 60
                self.scheduler.add_job(
                    self._fire_warning,
                    CronTrigger(
                        hour=trigger_hour, minute=trigger_minute, timezone=UTC
                    ),
                    args=[guild_id, warn_minutes],
                    id=_warn_job_id(guild_id, hour, warn_minutes),
                    replace_existing=True,
                    misfire_grace_time=60,
                )
        log.info(
            "Scheduler: guild=%d hours=%s warnings=%s", guild_id, hours, warnings
        )

    def _clear_guild_jobs(self, guild_id: int) -> None:
        prefix = f"g{guild_id}:"
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith(prefix):
                job.remove()

    # ---- callbacks -------------------------------------------------------

    async def _fire_rollover(self, guild_id: int, hour: int) -> None:
        now = datetime.now(tz=UTC)
        log.info("session rollover guild=%d hour=%d", guild_id, hour)
        async with self.bot.db() as session:
            settings = SettingsService(session)
            maintenance = bool(
                await settings.get(guild_id, Keys.MAINTENANCE_MODE, False)
            )
            svc = SessionService(session)
            ended_id, new_id = await svc.end_session(
                guild_id, reason=SessionEndReason.AUTO, when=now
            )
            if maintenance:
                log.info(
                    "session rolled silently (maintenance) guild=%d", guild_id
                )
                return
            embed = await _build_rollover_embed(
                session,
                bot=self.bot,
                guild_id=guild_id,
                ended_id=ended_id,
                new_id=new_id,
                now=now,
            )
            if embed is not None:
                await broadcast_to_guild(
                    session, self.bot, guild_id=guild_id, embed=embed
                )

    async def _fire_warning(self, guild_id: int, warn_minutes: int) -> None:
        now = datetime.now(tz=UTC)
        async with self.bot.db() as session:
            settings = SettingsService(session)
            reset_hours = [
                int(h)
                for h in await settings.get(
                    guild_id, Keys.RESET_HOURS_UTC, [7, 15, 23]
                )
            ]
        next_reset = next_reset_at(reset_hours, now=now)
        delta = (next_reset - now).total_seconds()
        if abs(delta - warn_minutes * 60) > 120:
            return
        embed = _simple_warning_embed(next_reset - now)
        async with self.bot.db() as session:
            if await SettingsService(session).get(
                guild_id, Keys.MAINTENANCE_MODE, False
            ):
                return
            await broadcast_to_guild(
                session, self.bot, guild_id=guild_id, embed=embed
            )


async def _build_rollover_embed(
    session,
    *,
    bot: StankBot,
    guild_id: int,
    ended_id: int | None,
    new_id: int | None,
    now: datetime,
) -> discord.Embed | None:
    settings = SettingsService(session)
    reset_hours = [
        int(h)
        for h in await settings.get(guild_id, Keys.RESET_HOURS_UTC, [7, 15, 23])
    ]
    continues = bool(
        await settings.get(guild_id, Keys.CHAIN_CONTINUES_ACROSS_SESSIONS, True)
    )
    next_reset = next_reset_at(reset_hours, now=now)

    prev_top_sp_name = "—"
    prev_top_sp = 0
    prev_top_pp_name = "—"
    prev_top_pp = 0
    prev_rec_len = 0
    prev_rec_unique = 0
    if ended_id is not None:
        summary = await history_service.session_summary(session, guild_id, ended_id)
        if summary is not None:
            if summary.top_earner is not None:
                uid, sp = summary.top_earner
                prev_top_sp_name = await embed_builders.display_name_of(
                    session, guild_id, uid
                )
                prev_top_sp = sp
            if summary.top_breaker is not None:
                uid, pp = summary.top_breaker
                prev_top_pp_name = await embed_builders.display_name_of(
                    session, guild_id, uid
                )
                prev_top_pp = pp

    # Previous session record — best we can get cheaply is the "session"
    # scope record which is baselined to the surviving chain at rollover;
    # for the just-ended session that's still valid until the new session
    # writes a fresh baseline. Read it before any rebaseline happens.
    # (We're inside the same transaction as end_session, before commit.)
    from stankbot.db.repositories import records as records_repo

    # primary altar for the guild — TODO multi-altar rollover later.
    from stankbot.db.repositories import altars as altars_repo

    altar = await altars_repo.primary(session, guild_id)
    altar_channel = ""
    if altar is not None:
        channel = bot.get_channel(altar.channel_id)
        altar_channel = getattr(channel, "name", "") if channel else ""
    if altar is not None:
        rec_row = await records_repo.get(
            session,
            guild_id=guild_id,
            altar_id=altar.id,
            scope=RecordScope.SESSION,
        )
        if rec_row is not None:
            prev_rec_len = rec_row.chain_length
            prev_rec_unique = rec_row.unique_count
        alltime_row = await records_repo.get(
            session,
            guild_id=guild_id,
            altar_id=altar.id,
            scope=RecordScope.ALLTIME,
        )
        alltime_len = alltime_row.chain_length if alltime_row else 0
        alltime_unique = alltime_row.unique_count if alltime_row else 0
    else:
        alltime_len = 0
        alltime_unique = 0

    all_sp_name, all_sp = await embed_builders.alltime_top_sp(session, guild_id)
    all_pp_name, all_pp = await embed_builders.alltime_top_pp(session, guild_id)

    stank_emoji = embed_builders.resolve_stank_emoji(None, altar)
    continuity_summary = (
        f"The chain continues — keep the pressure on. {stank_emoji}"
        if continues
        else "Fresh start — who claims position 1?"
    )
    continuity_summary += " Cooldowns reset — Team Player bonus up for grabs."

    from stankbot.db.repositories import events as events_repo

    ended_seq = (
        await events_repo.count_session_starts(session, guild_id, up_to_id=ended_id)
        if ended_id is not None
        else 0
    )
    new_seq = ended_seq + 1 if new_id is not None else 0

    vars_ = embed_builders.NewSessionVars(
        new_session_number=new_seq,
        ended_session_number=ended_seq,
        chain_continuity_summary=continuity_summary,
        session_top_player=prev_top_sp_name,
        session_top_sp=prev_top_sp,
        session_top_breaker=prev_top_pp_name,
        session_top_breaker_pp=prev_top_pp,
        prev_session_record=prev_rec_len,
        prev_session_record_unique=prev_rec_unique,
        alltime_record=alltime_len,
        alltime_record_unique=alltime_unique,
        alltime_top_sp_player=all_sp_name,
        alltime_top_sp=all_sp,
        alltime_top_pp_player=all_pp_name,
        alltime_top_pp=all_pp,
        next_reset_in=humanize_duration((next_reset - now).total_seconds()),
    )
    return embed_builders.build_new_session_embed(
        vars_,
        altar_channel=altar_channel,
        altar_channel_id=altar.channel_id if altar else 0,
        board_url=embed_builders.board_url_for(
            bot.config.oauth_redirect_uri, guild_id
        ),
    )


def _rollover_job_id(guild_id: int, hour: int) -> str:
    return f"g{guild_id}:rollover:{hour:02d}"


def _warn_job_id(guild_id: int, hour: int, warn: int) -> str:
    return f"g{guild_id}:warn:{hour:02d}:{warn}"


def _simple_warning_embed(remaining: timedelta) -> discord.Embed:
    return discord.Embed(
        title="⏳ Session ending soon",
        description=f"Session rolls in **{humanize_duration(remaining.total_seconds())}**.",
        color=discord.Color.from_str("#f59e0b"),
    )
