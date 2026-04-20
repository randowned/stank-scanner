"""Chain listener cog — Discord events → ChainService.

Watches altar channels for messages and reactions, hands each event to
``ChainService`` framework-agnostically, then turns the returned
``ChainResult`` into visible side effects (chain-break notices, record
announcements, public cooldown notices — all posted back into the altar
channel, non-ephemerally).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from stankbot.db.models import RecordScope
from stankbot.db.repositories import altars as altars_repo
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import guilds as guilds_repo
from stankbot.services import embed_builders
from stankbot.services.announcement_service import broadcast_to_guild
from stankbot.services.chain_service import ChainOutcome, ChainService, StankInput
from stankbot.services.session_service import SessionService
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.utils.time_utils import humanize_duration

if TYPE_CHECKING:
    from stankbot.bot import StankBot
    from stankbot.db.models import Altar

log = logging.getLogger(__name__)


def _is_stank_message(message: discord.Message, altar: Altar) -> bool:
    """A 'stank' is a sticker whose name matches the altar's pattern,
    with no extra text.

    Text alongside the sticker is treated as noise (and will break an
    open chain via the listener's non-stank branch).
    """
    if message.content and message.content.strip():
        return False
    if not message.stickers:
        return False
    pattern = (altar.sticker_name_pattern or "").lower()
    if not pattern:
        return False
    return any(pattern in (s.name or "").lower() for s in message.stickers)


def _is_altar_reaction(emoji: discord.PartialEmoji, altar: Altar) -> bool:
    """True if a reaction emoji is the one configured for this altar."""
    if altar.reaction_emoji_id is not None:
        return emoji.id == altar.reaction_emoji_id
    if altar.reaction_emoji_name:
        return (emoji.name or "") == altar.reaction_emoji_name
    return False


class ChainListener(commands.Cog):
    def __init__(self, bot: StankBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        try:
            await self._handle_message(message)
        except Exception:
            log.exception(
                "unhandled error in on_message guild=%s channel=%s",
                getattr(message.guild, "id", None),
                message.channel.id,
            )

    async def _handle_message(self, message: discord.Message) -> None:
        async with self.bot.db() as session:
            altar = await altars_repo.for_guild(session, message.guild.id)
            if altar is None:
                log.info("on_message: no altar configured guild=%d", message.guild.id)
                return
            if altar.channel_id != message.channel.id:
                return
            settings = SettingsService(session)
            maintenance = bool(
                await settings.get(
                    message.guild.id, Keys.MAINTENANCE_MODE, False
                )
            )
            await guilds_repo.ensure(session, message.guild.id, message.guild.name)
            session_svc = SessionService(session)
            chain_svc = ChainService(session, session_id_provider=session_svc)

            await session_svc.ensure_started(message.guild.id, when=message.created_at)

            config = await settings.effective_scoring(message.guild.id, altar)
            stank_input = StankInput(
                guild_id=message.guild.id,
                altar=altar,
                message_id=message.id,
                author_id=message.author.id,
                author_display_name=message.author.display_name,
                is_stank=_is_stank_message(message, altar),
                created_at=message.created_at,
            )
            result = await chain_svc.process(stank_input, config)

            if result.outcome == ChainOutcome.VALID_STANK:
                log.info(
                    "valid stank guild=%d altar=%d user=%d length=%d maintenance=%s",
                    message.guild.id,
                    altar.id,
                    message.author.id,
                    result.chain_length,
                    maintenance,
                )
                if not maintenance:
                    await self._auto_react(message, altar)
                return

            if result.outcome == ChainOutcome.COOLDOWN:
                if not maintenance:
                    await self._auto_react(message, altar)
                    await self._post_cooldown(
                        session,
                        message,
                        config.cooldown_seconds,
                        result.cooldown_seconds_remaining,
                    )
                return

            if result.outcome == ChainOutcome.CHAIN_BREAK:
                log.info(
                    "chain broken guild=%d altar=%d breaker=%d length=%d pp=%d maintenance=%s",
                    message.guild.id,
                    altar.id,
                    message.author.id,
                    result.broken_length,
                    result.pp_awarded,
                    maintenance,
                )
                if not maintenance:
                    await self._post_chain_break(session, message, altar, result)
                    if result.record_broken or result.alltime_record_broken:
                        await self._post_record(session, message, altar, result)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == self.bot.user.id:  # type: ignore[union-attr]
            return
        emoji = payload.emoji

        async with self.bot.db() as session:
            altar = await altars_repo.for_guild(session, payload.guild_id)
            if altar is None or altar.channel_id != payload.channel_id:
                return
            settings = SettingsService(session)
            enabled = await settings.get(
                payload.guild_id, Keys.ENABLE_REACTION_BONUS, True
            )
            if not enabled:
                return
            if not _is_altar_reaction(emoji, altar):
                return

            session_svc = SessionService(session)
            chain_svc = ChainService(session, session_id_provider=session_svc)

            config = await settings.effective_scoring(payload.guild_id, altar)
            sticker_key = emoji.id or -abs(hash(emoji.name or "")) % (10**12)
            await chain_svc.award_reaction_bonus(
                guild_id=payload.guild_id,
                altar=altar,
                message_id=payload.message_id,
                user_id=payload.user_id,
                sticker_id=sticker_key,
                config=config,
            )

    # ---- announcement helpers -------------------------------------------

    async def _auto_react(
        self, message: discord.Message, altar: Altar
    ) -> None:
        """Add the altar's configured reaction emoji to a valid stank.

        Custom emoji: resolved via ``reaction_emoji_id`` (falls back to
        ``PartialEmoji`` when the guild object lacks it). Unicode glyph:
        use ``reaction_emoji_name`` directly.
        """
        emoji: discord.Emoji | discord.PartialEmoji | str | None = None
        if altar.reaction_emoji_id is not None:
            guild_emoji = (
                message.guild.get_emoji(altar.reaction_emoji_id)
                if message.guild is not None
                else None
            )
            if guild_emoji is not None:
                emoji = guild_emoji
            else:
                emoji = discord.PartialEmoji(
                    name=altar.reaction_emoji_name or "_",
                    id=altar.reaction_emoji_id,
                    animated=bool(altar.reaction_emoji_animated),
                )
        elif altar.reaction_emoji_name:
            emoji = altar.reaction_emoji_name
        if emoji is None:
            return
        try:
            await message.add_reaction(emoji)
        except discord.DiscordException:
            log.exception("failed to auto-react to stank message")

    async def _post_cooldown(
        self,
        session,
        message: discord.Message,
        cooldown_total: int,
        cooldown_remaining: int,
    ) -> None:
        embed = embed_builders.build_cooldown_embed(
            target_display_name=message.author.display_name,
            cooldown_remaining=humanize_duration(cooldown_remaining),
            cooldown_total=humanize_duration(cooldown_total),
            altar_channel=getattr(message.channel, "name", ""),
            altar_channel_id=message.channel.id,
            board_url=embed_builders.board_url_for(
                self.bot.config.oauth_redirect_uri, message.guild.id
            ),
        )
        try:
            await broadcast_to_guild(
                session, self.bot, guild_id=message.guild.id, embed=embed
            )
        except discord.DiscordException:
            log.exception("failed to post cooldown notice")

    async def _post_chain_break(
        self,
        session,
        message: discord.Message,
        altar: Altar,
        result,
    ) -> None:
        starter_uid, starter_name, starter_sp = await _starter_details(
            session, guild_id=message.guild.id, chain=await _fetch_chain_for_break(session, altar, message.id)
        )
        finish_name = await embed_builders.display_name_of(
            session, message.guild.id, result.finish_bonus_user_id
        )
        embed = embed_builders.build_chain_break_embed(
            altar=altar,
            guild=message.guild,
            altar_channel=getattr(message.channel, "name", ""),
            board_url=embed_builders.board_url_for(
                self.bot.config.oauth_redirect_uri, message.guild.id
            ),
            vars_=embed_builders.ChainBreakVars(
                breaker_name=message.author.display_name,
                broken_length=result.broken_length,
                broken_unique=result.chain_unique or 0,
                pp_awarded=result.pp_awarded,
                starter_name=starter_name,
                starter_sp=starter_sp,
                finish_recipient_name=finish_name,
                finish_bonus_sp=result.sp_awarded,
            ),
        )
        try:
            await broadcast_to_guild(
                session, self.bot, guild_id=message.guild.id, embed=embed
            )
        except discord.DiscordException:
            log.exception("failed to post chain-break announcement")

    async def _post_record(
        self,
        session,
        message: discord.Message,
        altar: Altar,
        result,
    ) -> None:
        alltime_len, alltime_unique = await embed_builders.current_record(
            session,
            guild_id=message.guild.id,
            altar_id=altar.id,
            scope=RecordScope.ALLTIME,
        )
        _, starter_name, starter_sp = await _starter_details(
            session,
            guild_id=message.guild.id,
            chain=await _fetch_chain_for_break(session, altar, message.id),
        )
        embed = embed_builders.build_record_embed(
            altar=altar,
            guild=message.guild,
            altar_channel=getattr(message.channel, "name", ""),
            board_url=embed_builders.board_url_for(
                self.bot.config.oauth_redirect_uri, message.guild.id
            ),
            vars_=embed_builders.RecordBreakVars(
                length=result.broken_length,
                unique=result.chain_unique or 0,
                alltime_length=alltime_len,
                alltime_unique=alltime_unique,
                session_broken=result.record_broken,
                alltime_broken=result.alltime_record_broken,
                starter_name=starter_name,
                starter_sp=starter_sp,
            ),
        )
        try:
            await broadcast_to_guild(
                session, self.bot, guild_id=message.guild.id, embed=embed
            )
        except discord.DiscordException:
            log.exception("failed to post record announcement")


async def _fetch_chain_for_break(session, altar: Altar, message_id: int):
    """Return the chain that was just broken — look up by the break message id."""
    # chain_break event carries the chain_id; fall back to most recent broken chain for altar.
    from sqlalchemy import select

    from stankbot.db.models import Chain

    stmt = (
        select(Chain)
        .where(Chain.guild_id == altar.guild_id, Chain.altar_id == altar.id)
        .order_by(Chain.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _starter_details(session, *, guild_id: int, chain) -> tuple[int | None, str, int]:
    if chain is None:
        return None, "—", 0
    starter_id = chain.starter_user_id
    name = await embed_builders.display_name_of(session, guild_id, starter_id)
    sp, _pp = await events_repo.sp_pp_totals(session, guild_id, starter_id)
    return starter_id, name, int(sp)


async def setup(bot: StankBot) -> None:
    await bot.add_cog(ChainListener(bot))
