"""``/stank`` user command group — board, points, cooldown, help.

One ``commands.GroupCog`` hosts every ``/stank <sub>`` command because
discord.py binds an ``app_commands.Group`` to a single class; splitting
subcommands across cogs fights the framework. Presentation helpers
live in ``services/`` modules so the web dashboard can reuse them.

All replies are ephemeral by default — see AGENTS.md (slash-first,
ephemeral-by-default principle).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from stankbot.db.repositories import altars as altars_repo
from stankbot.db.repositories import cooldowns as cooldowns_repo
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import players as players_repo
from stankbot.services import achievements as achievements_svc
from stankbot.services import embed_builders as _eb
from stankbot.services import history_service
from stankbot.services.board_renderer import render_board_embed
from stankbot.services.board_service import build_board_state
from stankbot.services.default_templates import (
    BOARD_EMBED,
    COOLDOWN_EMBED,
    POINTS_EMBED,
)
from stankbot.services.session_service import SessionService
from stankbot.services.settings_service import Keys, SettingsService
from stankbot.cogs._checks import (
    SilentlySuppressed,
    WrongChannel,
    is_interaction_admin,
    maintenance_mode_enabled,
    silently_suppress,
)
from stankbot.db.models import ChannelBinding, ChannelPurpose
from stankbot.services.template_engine import RenderContext, render_embed
from stankbot.utils.time_utils import humanize_duration
from sqlalchemy import select

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)


def _resolve_guild_emoji(guild: discord.Guild, name: str) -> str | None:
    """Return Discord emoji markup ``<:Name:id>`` for a case-insensitive
    match on ``name``, or None if the guild has no such custom emoji.

    Embeds only render custom emojis via the full ``<:Name:id>`` syntax;
    bare ``:name:`` shortcodes are rendered as plain text.
    """
    lowered = name.lower()
    for emoji in guild.emojis:
        if emoji.name.lower() == lowered:
            prefix = "a" if emoji.animated else ""
            return f"<{prefix}:{emoji.name}:{emoji.id}>"
    return None


class StankCommands(commands.GroupCog, name="stank"):
    """Top-level ``/stank`` user commands."""

    history = app_commands.Group(
        name="history", description="Player / chain / session history."
    )

    def __init__(self, bot: StankBot) -> None:
        self.bot = bot
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restrict ``/stank`` user commands to announcement channels."""
        if interaction.guild is None or interaction.channel is None:
            return True
        if await maintenance_mode_enabled(self.bot, interaction.guild.id):
            if not await is_interaction_admin(interaction):
                await silently_suppress(interaction)
                raise SilentlySuppressed()
        async with self.bot.db() as session:
            rows = await session.execute(
                select(ChannelBinding.channel_id).where(
                    ChannelBinding.guild_id == interaction.guild.id,
                    ChannelBinding.purpose == ChannelPurpose.ANNOUNCEMENTS.value,
                )
            )
            allowed = [int(r) for r in rows.scalars()]
        if not allowed or interaction.channel.id in allowed:
            return True
        raise WrongChannel(allowed)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, SilentlySuppressed):
            return
        if isinstance(error, WrongChannel):
            mentions = ", ".join(f"<#{cid}>" for cid in error.allowed_channel_ids)
            msg = f"Use this command in {mentions}."
        elif isinstance(error, app_commands.CheckFailure):
            msg = "You can't use this command here."
        else:
            log.exception("stank command error", exc_info=error)
            msg = f"Command failed: `{type(error).__name__}`."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    # ---- /stank board ----------------------------------------------------

    @app_commands.command(
        name="board", description="Show the current Stank board for this server."
    )
    async def board(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works inside a server.", ephemeral=True
            )
            return
        ephemeral = await maintenance_mode_enabled(self.bot, interaction.guild.id)
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)

        async with self.bot.db() as session:
            altar = await altars_repo.primary(session, interaction.guild.id)
            if altar is None:
                await interaction.followup.send(
                    "No altar is configured yet. An admin needs to run "
                    "`/stank-admin altar set` first.",
                    ephemeral=True,
                )
                return

            settings = SettingsService(session)
            template = await settings.get(
                interaction.guild.id, Keys.BOARD_EMBED, BOARD_EMBED
            )
            state = await build_board_state(
                session,
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name,
                altar=altar,
                stank_emoji_override=_resolve_guild_emoji(
                    interaction.guild, "Stank"
                ),
            )

        embed = render_board_embed(
            template,
            state,
            dashboard_url=_eb.board_url_for(
                self.bot.config.oauth_redirect_uri, interaction.guild.id
            ),
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    # ---- /stank points ---------------------------------------------------

    @app_commands.command(
        name="points",
        description="Show your SP/PP — or another player's by rank or mention.",
    )
    @app_commands.describe(
        rank="1-indexed rank on the session leaderboard",
        user="Show points for a specific user",
    )
    async def points(
        self,
        interaction: discord.Interaction,
        rank: int | None = None,
        user: discord.User | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works inside a server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        async with self.bot.db() as session:
            session_svc = SessionService(session)
            session_id = await session_svc.current(interaction.guild.id)

            target_id: int | None = None
            if user is not None:
                target_id = user.id
            elif rank is not None:
                board = await events_repo.leaderboard(
                    session,
                    interaction.guild.id,
                    session_id=session_id,
                    limit=rank,
                )
                if rank < 1 or rank > len(board):
                    await interaction.followup.send(
                        f"No player at rank {rank}.", ephemeral=True
                    )
                    return
                target_id = board[rank - 1][0]
            else:
                target_id = interaction.user.id

            sp, pp = await events_repo.sp_pp_totals(
                session, interaction.guild.id, target_id, session_id=session_id
            )
            user_rank = await events_repo.user_rank(
                session,
                interaction.guild.id,
                target_id,
                session_id=session_id,
            )
            started = await events_repo.chains_started(
                session, interaction.guild.id, target_id
            )
            broken = await events_repo.chains_broken(
                session, interaction.guild.id, target_id
            )
            last_stank = await events_repo.last_stank_at(
                session, interaction.guild.id, target_id
            )
            from stankbot.cogs._identity import ensure_player

            await ensure_player(
                session,
                self.bot,
                guild_id=interaction.guild.id,
                user_id=target_id,
                hint=user,
            )
            player = await players_repo.get_or_create(
                session, interaction.guild.id, target_id
            )
            badge_keys = await achievements_svc.badges_for(
                session, interaction.guild.id, target_id
            )
            settings = SettingsService(session)
            template = await settings.get(
                interaction.guild.id, Keys.POINTS_EMBED, POINTS_EMBED
            )

        target = user if user is not None else interaction.client.get_user(target_id)
        display_name = (
            (target.display_name if target is not None else None)
            or player.display_name
            or str(target_id)
        )
        avatar_url = (
            str(target.display_avatar.url) if target is not None else ""
        )
        net = sp - pp
        ctx = RenderContext(
            variables={
                "target_display_name": display_name,
                "target_avatar_url": avatar_url,
                "rank": user_rank or "—",
                "net_sp_sign": "+" if net >= 0 else "",
                "net_sp": net,
                "earned_sp": sp,
                "punishments": pp,
                "chains_started": started,
                "chains_broken": broken,
                "badge_list": _format_badge_list(badge_keys),
                "last_stank_rel": (
                    _relative_time(last_stank) if last_stank else "never"
                ),
            }
        )
        embed = render_embed(template, ctx)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---- /stank cooldown -------------------------------------------------

    @app_commands.command(
        name="cooldown", description="How long until you can stank again?"
    )
    async def cooldown(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works inside a server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        async with self.bot.db() as session:
            altar = await altars_repo.primary(session, interaction.guild.id)
            if altar is None:
                await interaction.followup.send(
                    "No altar is configured yet.", ephemeral=True
                )
                return
            settings = SettingsService(session)
            config = await settings.effective_scoring(interaction.guild.id, altar)
            last = await cooldowns_repo.get_last_stank(
                session,
                guild_id=interaction.guild.id,
                altar_id=altar.id,
                user_id=interaction.user.id,
            )
            remaining = cooldowns_repo.seconds_remaining(
                last,
                cooldown_seconds=config.cooldown_seconds,
                now=datetime.now(tz=UTC),
            )
            template = await settings.get(
                interaction.guild.id, Keys.COOLDOWN_EMBED, COOLDOWN_EMBED
            )

        if remaining == 0:
            await interaction.followup.send(
                "You can stank right now.", ephemeral=True
            )
            return

        altar_channel_obj = interaction.guild.get_channel(altar.channel_id) if altar else None
        from stankbot.services import embed_builders as _eb

        ctx = RenderContext(
            variables={
                "target_display_name": interaction.user.display_name,
                "cooldown_remaining": humanize_duration(remaining),
                "cooldown_total": humanize_duration(config.cooldown_seconds),
                "altar_channel": getattr(altar_channel_obj, "name", ""),
                "altar_channel_id": altar.channel_id if altar else 0,
                "altar_channel_mention": _eb.altar_channel_mention(
                    altar.channel_id if altar else None
                ),
                "board_url": _eb.board_url_for(
                    self.bot.config.oauth_redirect_uri, interaction.guild.id
                ),
            }
        )
        embed = render_embed(template, ctx)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---- /stank help -----------------------------------------------------

    @app_commands.command(
        name="help", description="Rules, scoring, and available commands."
    )
    async def help_(self, interaction: discord.Interaction) -> None:
        # Built programmatically — not a user-editable template.
        embed = discord.Embed(
            title="StankBot help",
            color=discord.Color.from_str("#a47cff"),
            description=(
                "Drop the altar sticker in the altar channel to add to the "
                "chain. Anything else in that channel breaks the chain."
            ),
        )
        embed.add_field(
            name="Commands",
            value=(
                "`/stank board` — current leaderboard and chain state\n"
                "`/stank points` — your SP/PP breakdown\n"
                "`/stank cooldown` — time until you can stank again\n"
                "`/stank help` — this message"
            ),
            inline=False,
        )
        embed.add_field(
            name="Scoring",
            value=(
                "• **SP** for each valid stank (+position bonus, +starter bonus)\n"
                "• **Finish bonus** to the last non-breaker when a chain ends\n"
                "• **PP** penalty for breaking a chain (scales with length)\n"
                "• Reactions with the altar sticker award a small bonus — once"
            ),
            inline=False,
        )
        embed.add_field(
            name="Chain rules",
            value=(
                "• One stank per cooldown window per altar\n"
                "• Any non-sticker message in the altar channel breaks the chain\n"
                "• Chain survives session rollovers by default"
            ),
            inline=False,
        )
        embed.set_footer(text="StankBot")
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # ---- /stank history --------------------------------------------------

    @history.command(name="me", description="Your SP/PP trend and chain stats.")
    async def history_me(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self._send_user_history(interaction, interaction.user.id)

    @history.command(name="user", description="Another player's history.")
    async def history_user(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if interaction.guild is None:
            return
        await self._send_user_history(interaction, user.id)

    @history.command(name="chain", description="Replay a specific chain by id.")
    async def history_chain(
        self, interaction: discord.Interaction, chain_id: int
    ) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.bot.db() as session:
            summary = await history_service.chain_summary(
                session, interaction.guild.id, chain_id
            )
            names: dict[int, str] = {}
            if summary is not None:
                uid_set = {summary.starter_user_id, *(uid for uid, _ in summary.contributors)}
                if summary.broken_by_user_id is not None:
                    uid_set.add(summary.broken_by_user_id)
                from sqlalchemy import select

                from stankbot.db.models import Player

                rows = (
                    await session.execute(
                        select(Player.user_id, Player.display_name).where(
                            Player.guild_id == interaction.guild.id,
                            Player.user_id.in_(uid_set),
                        )
                    )
                ).all()
                names = {int(uid): name or str(uid) for uid, name in rows}

        if summary is None:
            await interaction.followup.send(
                f"No chain `{chain_id}` in this server.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"⛓️ Chain #{summary.chain_id}",
            color=discord.Color.from_str("#a47cff"),
        )
        embed.add_field(name="Length", value=str(summary.length), inline=True)
        embed.add_field(
            name="Unique", value=str(summary.unique_contributors), inline=True
        )
        starter = names.get(summary.starter_user_id, str(summary.starter_user_id))
        embed.add_field(name="Starter", value=starter, inline=True)
        if summary.broken_by_user_id is not None:
            breaker = names.get(
                summary.broken_by_user_id, str(summary.broken_by_user_id)
            )
            embed.add_field(name="Broken by", value=breaker, inline=True)
        embed.add_field(
            name="Started",
            value=f"<t:{int(summary.started_at.timestamp())}:f>"
            if summary.started_at
            else "—",
            inline=True,
        )
        if summary.broken_at:
            embed.add_field(
                name="Ended",
                value=f"<t:{int(summary.broken_at.timestamp())}:f>",
                inline=True,
            )
        if summary.contributors:
            top_lines = [
                f"`{i}.` {names.get(uid, str(uid))} — {n} stanks"
                for i, (uid, n) in enumerate(summary.contributors[:10], 1)
            ]
            embed.add_field(
                name="Top contributors", value="\n".join(top_lines), inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @history.command(name="session", description="Summary of a past session.")
    async def history_session(
        self, interaction: discord.Interaction, session_id: int
    ) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.bot.db() as session:
            summary = await history_service.session_summary(
                session, interaction.guild.id, session_id
            )
            names: dict[int, str] = {}
            if summary is not None:
                uids = {
                    pair[0]
                    for pair in (summary.top_earner, summary.top_breaker)
                    if pair is not None
                }
                if uids:
                    from sqlalchemy import select

                    from stankbot.db.models import Player

                    rows = (
                        await session.execute(
                            select(Player.user_id, Player.display_name).where(
                                Player.guild_id == interaction.guild.id,
                                Player.user_id.in_(uids),
                            )
                        )
                    ).all()
                    names = {int(uid): name or str(uid) for uid, name in rows}

        if summary is None:
            await interaction.followup.send(
                f"No session `{session_id}` in this server.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 Session #{summary.session_id}",
            color=discord.Color.from_str("#64748b"),
        )
        if summary.started_at:
            embed.add_field(
                name="Started",
                value=f"<t:{int(summary.started_at.timestamp())}:f>",
                inline=True,
            )
        embed.add_field(
            name="Ended",
            value=(
                f"<t:{int(summary.ended_at.timestamp())}:f>"
                if summary.ended_at
                else "_still open_"
            ),
            inline=True,
        )
        embed.add_field(
            name="Chains started", value=str(summary.chains_started), inline=True
        )
        embed.add_field(
            name="Chains broken", value=str(summary.chains_broken), inline=True
        )
        if summary.top_earner:
            uid, sp = summary.top_earner
            embed.add_field(
                name="Top earner",
                value=f"{names.get(uid, str(uid))} · **{sp} SP**",
                inline=True,
            )
        if summary.top_breaker:
            uid, pp = summary.top_breaker
            embed.add_field(
                name="Top breaker",
                value=f"{names.get(uid, str(uid))} · **{pp} PP**",
                inline=True,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _send_user_history(
        self, interaction: discord.Interaction, user_id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.bot.db() as session:
            session_svc = SessionService(session)
            sid = await session_svc.current(interaction.guild.id)  # type: ignore[union-attr]
            session_stats = await history_service.user_summary(
                session, interaction.guild.id, user_id, session_id=sid  # type: ignore[union-attr]
            )
            alltime = await history_service.user_summary(
                session, interaction.guild.id, user_id  # type: ignore[union-attr]
            )
            badge_keys = await achievements_svc.badges_for(
                session, interaction.guild.id, user_id  # type: ignore[union-attr]
            )

        embed = discord.Embed(
            title=f"📈 {session_stats.display_name}",
            color=discord.Color.from_str("#a47cff"),
        )
        embed.add_field(
            name="Session SP", value=str(session_stats.earned_sp), inline=True
        )
        embed.add_field(
            name="Session PP", value=str(session_stats.punishments), inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="All-time SP", value=str(alltime.earned_sp), inline=True)
        embed.add_field(
            name="All-time PP", value=str(alltime.punishments), inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(
            name="Chains started", value=str(alltime.chains_started), inline=True
        )
        embed.add_field(
            name="Chains broken", value=str(alltime.chains_broken), inline=True
        )
        embed.add_field(
            name="🏅 Badges",
            value=_format_badge_list(badge_keys),
            inline=False,
        )
        if alltime.last_stank_at:
            embed.set_footer(
                text=f"Last stank: {alltime.last_stank_at.isoformat(timespec='minutes')}"
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


def _format_badge_list(keys: list[str]) -> str:
    if not keys:
        return "_No badges yet._"
    parts: list[str] = []
    for key in keys:
        defn = achievements_svc.definition(key)
        if defn is None:
            parts.append(f"`{key}`")
        else:
            parts.append(f"{defn.icon} **{defn.name}**")
    return " · ".join(parts)


def _relative_time(when: datetime) -> str:
    """Render ``when`` as a Discord relative-time marker (``<t:TS:R>``)."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return f"<t:{int(when.timestamp())}:R>"


async def setup(bot: StankBot) -> None:
    await bot.add_cog(StankCommands(bot))
