"""``/stank-admin`` command group — guild configuration + state ops.

Narrow by design: state mutations (reset, new-session, record-test, log),
channel/role/altar wiring, read-only config view. Anything that needs a
form (template bodies, scoring tuning, achievement rules) lives on the
web dashboard — see the approved plan.

Every mutation writes an ``audit_log`` row so the dashboard's audit page
and the slash ``log`` command can surface who did what.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from stankbot.cogs._checks import requires_admin
from stankbot.db.models import ChannelBinding, ChannelPurpose, SessionEndReason
from stankbot.db.repositories import altars as altars_repo
from stankbot.db.repositories import audit_log as audit_repo
from stankbot.db.repositories import guilds as guilds_repo
from stankbot.logging_setup import tail_log
from stankbot.services import embed_builders
from stankbot.services.permission_service import PermissionService
from stankbot.services.session_service import SessionService
from stankbot.services.settings_service import Keys, SettingsService

if TYPE_CHECKING:
    from stankbot.bot import StankBot

log = logging.getLogger(__name__)


_CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_~]+):(\d+)>")


def _parse_reaction_emoji(
    raw: str,
) -> tuple[int | None, str | None, bool] | None:
    """Parse a slash-command emoji arg into (id, name, animated).

    - ``<:Name:123>`` -> (123, "Name", False).
    - ``<a:Name:123>`` -> (123, "Name", True).
    - Unicode glyph like "🔥" -> (None, "🔥", False).
    - Anything else (e.g. literal ``:name:``) -> None.
    """
    raw = raw.strip()
    if not raw:
        return None
    m = _CUSTOM_EMOJI_RE.fullmatch(raw)
    if m:
        return int(m.group(3)), m.group(2), m.group(1) == "a"
    if len(raw) <= 8 and not raw.startswith(":"):
        return None, raw, False
    return None


class ConfirmView(discord.ui.View):
    """Two-button confirmation for destructive ops."""

    def __init__(self, invoker_id: int, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the admin who started this action can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        self.confirmed = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        self.confirmed = False
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class StankAdmin(commands.GroupCog, name="stank-admin"):
    """Admin commands — gated by ``requires_admin``."""

    # Subgroups declared as class attributes become nested command groups.
    announcements = app_commands.Group(
        name="announcements", description="Wire announcement channels."
    )
    admin_roles = app_commands.Group(
        name="admin-roles", description="Manage which roles count as admin."
    )
    admin_users = app_commands.Group(
        name="admin-users", description="Manage which users count as admin."
    )
    altar = app_commands.Group(
        name="altar", description="Configure the guild's altar."
    )
    config = app_commands.Group(
        name="config", description="Read-only configuration snapshot."
    )

    def __init__(self, bot: StankBot) -> None:
        self.bot = bot
        super().__init__()

    # ---- top-level ops ---------------------------------------------------

    @app_commands.command(
        name="dashboard", description="Post the dashboard login URL for this server."
    )
    @requires_admin()
    async def dashboard(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        url = self.bot.config.oauth_redirect_uri.rsplit("/", 2)[0]
        url = f"{url}/admin/settings"
        await interaction.response.send_message(
            f"Dashboard: {url}", ephemeral=True
        )

    @app_commands.command(
        name="maintenance",
        description="Toggle maintenance mode (silences bot for non-admins).",
    )
    @app_commands.describe(state="on = enable maintenance, off = disable.")
    @app_commands.choices(
        state=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    @requires_admin()
    async def maintenance(
        self,
        interaction: discord.Interaction,
        state: app_commands.Choice[str],
    ) -> None:
        if interaction.guild is None:
            return
        value = state.value == "on"
        async with self.bot.db() as session:
            await SettingsService(session).set(
                interaction.guild.id, Keys.MAINTENANCE_MODE, value
            )
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="maintenance_mode",
                payload={"enabled": value},
            )
        await interaction.response.send_message(
            f"Maintenance mode **{'enabled' if value else 'disabled'}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="new-session",
        description="End the current session; start a new one (chain persists).",
    )
    @requires_admin()
    async def new_session(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.bot.db() as session:
            await guilds_repo.ensure(
                session, interaction.guild.id, interaction.guild.name
            )
            svc = SessionService(session)
            ended, new_id = await svc.end_session(
                interaction.guild.id, reason=SessionEndReason.MANUAL
            )
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="new_session",
                payload={"ended_session_id": ended, "new_session_id": new_id},
            )
        await interaction.followup.send(
            f"Session rolled. Ended #{ended}, started #{new_id}.", ephemeral=True
        )

    @app_commands.command(
        name="reset",
        description="DESTRUCTIVE: wipe this server's chain, events, cooldowns.",
    )
    @requires_admin()
    async def reset(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            "⚠️ This wipes the chain, event log, cooldowns, and records for **this server**. "
            "Settings and altars are preserved. Confirm?",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.confirmed:
            await interaction.followup.send("Cancelled.", ephemeral=True)
            return

        async with self.bot.db() as session:
            from sqlalchemy import delete, select

            from stankbot.db.models import (
                Chain,
                ChainMessage,
                Cooldown,
                Event,
                PlayerBadge,
                PlayerTotal,
                ReactionAward,
                Record,
            )

            gid = interaction.guild.id
            # Delete chain_messages for this guild's chains first (no guild_id column).
            chain_ids = list(
                (
                    await session.execute(
                        select(Chain.id).where(Chain.guild_id == gid)
                    )
                ).scalars()
            )
            if chain_ids:
                await session.execute(
                    delete(ChainMessage).where(ChainMessage.chain_id.in_(chain_ids))
                )
            for model in (
                Event,
                Chain,
                Cooldown,
                ReactionAward,
                Record,
                PlayerTotal,
                PlayerBadge,
            ):
                await session.execute(
                    delete(model).where(model.guild_id == gid)  # type: ignore[attr-defined]
                )
            await audit_repo.append(
                session,
                guild_id=gid,
                actor_id=interaction.user.id,
                action="reset",
            )
        await interaction.followup.send("Board reset complete.", ephemeral=True)

    @app_commands.command(
        name="rebuild-from-history",
        description="DESTRUCTIVE: wipe and replay altar channel history.",
    )
    @requires_admin()
    async def rebuild(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        view = ConfirmView(interaction.user.id, timeout=60.0)
        await interaction.response.send_message(
            "⚠️ This **wipes** chains, events, cooldowns, records, and badges "
            "for this server, then replays every altar channel's full history. "
            "Can take minutes on active servers. Confirm?",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.confirmed:
            await interaction.followup.send("Cancelled.", ephemeral=True)
            return

        await interaction.followup.send(
            "Rebuild started. I'll post the summary here when it finishes.",
            ephemeral=True,
        )

        from stankbot.services import rebuild_service

        try:
            report = await rebuild_service.rebuild(self.bot, interaction.guild.id)
        except Exception as exc:  # noqa: BLE001 - surface to admin
            log.exception("rebuild failed for guild %d", interaction.guild.id)
            await interaction.followup.send(
                f"Rebuild failed: `{type(exc).__name__}: {exc}`.", ephemeral=True
            )
            return

        async with self.bot.db() as session:
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="rebuild_from_history",
                payload={
                    "altars": report.altars_scanned,
                    "messages": report.messages_scanned,
                    "valid_stanks": report.valid_stanks,
                    "chain_breaks": report.chain_breaks,
                    "reactions": report.reactions_awarded,
                },
            )
        await interaction.followup.send(
            f"Rebuild complete. Altars: **{report.altars_scanned}** · "
            f"Messages: **{report.messages_scanned}** · "
            f"Valid stanks: **{report.valid_stanks}** · "
            f"Breaks: **{report.chain_breaks}** · "
            f"Reactions: **{report.reactions_awarded}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="preview",
        description="Preview an embed with sample data (ephemeral).",
    )
    @app_commands.describe(kind="Which embed to preview.")
    @app_commands.choices(
        kind=[
            app_commands.Choice(name="record (session + all-time)", value="record"),
            app_commands.Choice(name="record (session only)", value="record-session"),
            app_commands.Choice(name="chain-break", value="chain-break"),
            app_commands.Choice(name="new-session", value="new-session"),
            app_commands.Choice(name="cooldown", value="cooldown"),
        ]
    )
    @requires_admin()
    async def preview(
        self, interaction: discord.Interaction, kind: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            return
        guild = interaction.guild
        async with self.bot.db() as session:
            altar = await altars_repo.primary(session, guild.id)

        display_name = interaction.user.display_name
        board_url = embed_builders.board_url_for(
            self.bot.config.oauth_redirect_uri, guild.id
        )
        altar_channel_id = altar.channel_id if altar else 0
        value = kind.value
        if value in ("record", "record-session"):
            alltime = value == "record"
            embed = embed_builders.build_record_embed(
                altar=altar,
                guild=guild,
                vars_=embed_builders.RecordBreakVars(
                    length=42,
                    unique=7,
                    alltime_length=100 if not alltime else 42,
                    alltime_unique=12 if not alltime else 7,
                    session_broken=True,
                    alltime_broken=alltime,
                    starter_name=display_name,
                    starter_sp=150,
                ),
                board_url=board_url,
            )
        elif value == "chain-break":
            embed = embed_builders.build_chain_break_embed(
                altar=altar,
                guild=guild,
                vars_=embed_builders.ChainBreakVars(
                    breaker_name=display_name,
                    broken_length=42,
                    broken_unique=7,
                    pp_awarded=109,
                    starter_name="@alice",
                    starter_sp=150,
                    finish_recipient_name="@bob",
                    finish_bonus_sp=15,
                ),
                board_url=board_url,
            )
        elif value == "new-session":
            embed = embed_builders.build_new_session_embed(
                embed_builders.NewSessionVars(
                    new_session_number=13,
                    ended_session_number=12,
                    chain_continuity_summary="The chain continues — keep the pressure on.",
                    session_top_player="@alice",
                    session_top_sp=412,
                    session_top_breaker="@bob",
                    session_top_breaker_pp=47,
                    prev_session_record=42,
                    prev_session_record_unique=7,
                    alltime_record=128,
                    alltime_record_unique=22,
                    alltime_top_sp_player="@alice",
                    alltime_top_sp=1820,
                    alltime_top_pp_player="@bob",
                    alltime_top_pp=312,
                    next_reset_in="7h 59m",
                ),
                altar_channel_id=altar_channel_id,
                board_url=board_url,
            )
        else:  # cooldown
            embed = embed_builders.build_cooldown_embed(
                target_display_name=display_name,
                cooldown_remaining="3m 20s",
                cooldown_total="20m",
                altar_channel_id=altar_channel_id,
                board_url=board_url,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="log", description="Tail recent bot log lines.")
    @app_commands.describe(lines="Number of lines (1-100).")
    @requires_admin()
    async def log_cmd(
        self, interaction: discord.Interaction, lines: int = 20
    ) -> None:
        lines = max(1, min(100, lines))
        entries = tail_log(lines)
        body = "\n".join(entries) if entries else "(no log entries yet)"
        # Discord message limit is 2000 chars; truncate front if needed.
        if len(body) > 1900:
            body = "…\n" + body[-1900:]
        await interaction.response.send_message(
            f"```\n{body}\n```", ephemeral=True
        )

    # ---- /stank-admin config ---------------------------------------------

    @config.command(name="view", description="Snapshot of current settings.")
    @requires_admin()
    async def config_view(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            settings = SettingsService(session)
            snapshot = await settings.all_for_guild(interaction.guild.id)
            altar_list = await altars_repo.list_for_guild(
                session, interaction.guild.id, enabled_only=False
            )

        lines = ["**Altar:**"]
        if altar_list:
            a = altar_list[0]
            lines.append(
                f"  <#{a.channel_id}> pattern=`{a.sticker_name_pattern}` "
                f"emoji={a.display_name or '—'} enabled={a.enabled}"
            )
        else:
            lines.append("  _not configured_")

        lines.append("")
        lines.append("**Scoring / sessions:**")
        for key in (
            Keys.SP_FLAT,
            Keys.SP_POSITION_BONUS,
            Keys.SP_STARTER_BONUS,
            Keys.SP_FINISH_BONUS,
            Keys.SP_REACTION,
            Keys.PP_BREAK_BASE,
            Keys.PP_BREAK_PER_STANK,
            Keys.RESTANK_COOLDOWN_SECONDS,
            Keys.RESET_HOURS_UTC,
            Keys.CHAIN_CONTINUES_ACROSS_SESSIONS,
            Keys.STANK_RANKING_ROWS,
            Keys.ENABLE_REACTION_BONUS,
        ):
            lines.append(f"  `{key}` = `{snapshot.get(key)}`")
        lines.append("")
        lines.append("Templates live on the dashboard.")
        await interaction.response.send_message(
            "\n".join(lines), ephemeral=True
        )

    # ---- /stank-admin announcements --------------------------------------

    @announcements.command(
        name="add", description="Add a channel to post announcements to."
    )
    @app_commands.describe(channel="Channel for announcements")
    @requires_admin()
    async def announcements_add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.CategoryChannel | discord.ForumChannel | discord.Thread,
    ) -> None:
        if interaction.guild is None:
            return
        purpose = ChannelPurpose.ANNOUNCEMENTS.value
        async with self.bot.db() as session:
            await guilds_repo.ensure(
                session, interaction.guild.id, interaction.guild.name
            )
            existing = await session.get(
                ChannelBinding, (interaction.guild.id, channel.id, purpose)
            )
            if existing is None:
                session.add(
                    ChannelBinding(
                        guild_id=interaction.guild.id,
                        channel_id=channel.id,
                        purpose=purpose,
                    )
                )
                action = "announcement_added"
            else:
                action = "announcement_add_noop"
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action=action,
                payload={"channel_id": channel.id},
            )
        await interaction.response.send_message(
            f"Bound {channel.mention} as an announcement channel.", ephemeral=True
        )

    @announcements.command(
        name="remove", description="Remove an announcement channel."
    )
    @requires_admin()
    async def announcements_remove(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.CategoryChannel | discord.ForumChannel | discord.Thread,
    ) -> None:
        if interaction.guild is None:
            return
        purpose = ChannelPurpose.ANNOUNCEMENTS.value
        async with self.bot.db() as session:
            row = await session.get(
                ChannelBinding, (interaction.guild.id, channel.id, purpose)
            )
            if row is None:
                await interaction.response.send_message(
                    f"{channel.mention} is not an announcement channel.",
                    ephemeral=True,
                )
                return
            await session.delete(row)
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="announcement_removed",
                payload={"channel_id": channel.id},
            )
        await interaction.response.send_message(
            f"Unbound {channel.mention}.", ephemeral=True
        )

    @announcements.command(
        name="list", description="List announcement channels."
    )
    @requires_admin()
    async def announcements_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        from sqlalchemy import select

        purpose = ChannelPurpose.ANNOUNCEMENTS.value
        async with self.bot.db() as session:
            stmt = select(ChannelBinding.channel_id).where(
                ChannelBinding.guild_id == interaction.guild.id,
                ChannelBinding.purpose == purpose,
            )
            rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            await interaction.response.send_message(
                "No announcement channels configured.", ephemeral=True
            )
            return
        lines = [f"- <#{cid}>" for cid in rows]
        await interaction.response.send_message(
            "**Announcement channels:**\n" + "\n".join(lines), ephemeral=True
        )

    # ---- /stank-admin admin-roles ----------------------------------------

    @admin_roles.command(name="add", description="Grant admin to a role.")
    @requires_admin()
    async def admin_roles_add(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            await guilds_repo.ensure(
                session, interaction.guild.id, interaction.guild.name
            )
            svc = PermissionService(session, owner_id=self.bot.config.owner_id)
            added = await svc.add_admin_role(interaction.guild.id, role.id)
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="admin_role_added" if added else "admin_role_noop",
                payload={"role_id": role.id},
            )
        msg = (
            f"{role.mention} granted admin."
            if added
            else f"{role.mention} was already admin."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @admin_roles.command(name="remove", description="Revoke admin from a role.")
    @requires_admin()
    async def admin_roles_remove(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            svc = PermissionService(session, owner_id=self.bot.config.owner_id)
            removed = await svc.remove_admin_role(interaction.guild.id, role.id)
            if removed:
                await audit_repo.append(
                    session,
                    guild_id=interaction.guild.id,
                    actor_id=interaction.user.id,
                    action="admin_role_removed",
                    payload={"role_id": role.id},
                )
        msg = (
            f"{role.mention} revoked."
            if removed
            else f"{role.mention} wasn't an admin role."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @admin_roles.command(name="list", description="List admin roles.")
    @requires_admin()
    async def admin_roles_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            svc = PermissionService(session, owner_id=self.bot.config.owner_id)
            ids = await svc.list_admin_roles(interaction.guild.id)
        if not ids:
            await interaction.response.send_message(
                "No admin roles configured. `Manage Guild` still grants admin.",
                ephemeral=True,
            )
            return
        lines = [f"- <@&{rid}>" for rid in ids]
        await interaction.response.send_message(
            "**Admin roles:**\n" + "\n".join(lines), ephemeral=True
        )

    # ---- /stank-admin admin-users ----------------------------------------

    @admin_users.command(name="add", description="Grant admin to a user.")
    @requires_admin()
    async def admin_users_add(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            await guilds_repo.ensure(
                session, interaction.guild.id, interaction.guild.name
            )
            svc = PermissionService(session, owner_id=self.bot.config.owner_id)
            added = await svc.add_admin_user(interaction.guild.id, user.id)
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="admin_user_added" if added else "admin_user_noop",
                payload={"user_id": user.id},
            )
        msg = (
            f"{user.mention} granted admin."
            if added
            else f"{user.mention} was already admin."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @admin_users.command(name="remove", description="Revoke admin from a user.")
    @requires_admin()
    async def admin_users_remove(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            svc = PermissionService(session, owner_id=self.bot.config.owner_id)
            removed = await svc.remove_admin_user(interaction.guild.id, user.id)
            if removed:
                await audit_repo.append(
                    session,
                    guild_id=interaction.guild.id,
                    actor_id=interaction.user.id,
                    action="admin_user_removed",
                    payload={"user_id": user.id},
                )
        msg = (
            f"{user.mention} revoked."
            if removed
            else f"{user.mention} wasn't an admin user."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @admin_users.command(name="list", description="List admin users.")
    @requires_admin()
    async def admin_users_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            svc = PermissionService(session, owner_id=self.bot.config.owner_id)
            ids = await svc.list_admin_users(interaction.guild.id)
        if not ids:
            await interaction.response.send_message(
                "No admin users configured.", ephemeral=True
            )
            return
        lines = [f"- <@{uid}>" for uid in ids]
        await interaction.response.send_message(
            "**Admin users:**\n" + "\n".join(lines), ephemeral=True
        )

    # ---- /stank-admin altar ----------------------------------------------

    @altar.command(
        name="set",
        description="Create or update this server's altar.",
    )
    @app_commands.describe(
        channel="Altar channel",
        sticker_name=(
            "Substring matched against sticker names (case-insensitive). "
            "E.g. 'stank' matches any sticker whose name contains 'stank'."
        ),
        reaction_emoji=(
            "Emoji the bot reacts with + awards a bonus for. Also used "
            "as {stank_emoji} in board/announcement templates. Type "
            "`:name:` in the arg and Discord expands it to the full tag."
        ),
    )
    @requires_admin()
    async def altar_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.CategoryChannel | discord.ForumChannel | discord.Thread,
        sticker_name: str = "stank",
        reaction_emoji: str | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        pattern = sticker_name.strip().lower()
        if not pattern:
            await interaction.response.send_message(
                "`sticker_name` can't be empty.", ephemeral=True
            )
            return

        emoji_id: int | None = None
        emoji_name: str | None = None
        emoji_animated = False
        if reaction_emoji:
            parsed = _parse_reaction_emoji(reaction_emoji)
            if parsed is None:
                await interaction.response.send_message(
                    "Couldn't read that emoji. Pick one from the emoji menu "
                    "(click the smiley icon in the arg field) or paste a "
                    "custom-emoji tag like `<:Stank:123>` / `<a:Stank:123>`.",
                    ephemeral=True,
                )
                return
            emoji_id, emoji_name, emoji_animated = parsed

        async with self.bot.db() as session:
            await guilds_repo.ensure(
                session, interaction.guild.id, interaction.guild.name
            )
            altar_row, created = await altars_repo.upsert(
                session,
                guild_id=interaction.guild.id,
                channel_id=channel.id,
                sticker_name_pattern=pattern,
                reaction_emoji_id=emoji_id,
                reaction_emoji_name=emoji_name,
                reaction_emoji_animated=emoji_animated,
            )
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="altar_created" if created else "altar_updated",
                payload={
                    "altar_id": altar_row.id,
                    "channel_id": channel.id,
                    "sticker_name_pattern": pattern,
                    "reaction_emoji_id": emoji_id,
                    "reaction_emoji_name": emoji_name,
                },
            )
        verb = "Created" if created else "Updated"
        reaction_desc = altar_row.display_name or "*(none)*"
        await interaction.response.send_message(
            f"{verb} altar in {channel.mention}.\n"
            f"- sticker pattern: `{pattern}`\n"
            f"- reaction emoji: {reaction_desc}\n"
            f"- `{{stank_emoji}}` in templates now renders as {reaction_desc}.",
            ephemeral=True,
        )

    @altar.command(name="remove", description="Remove this server's altar.")
    @requires_admin()
    async def altar_remove(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            altar_row = await altars_repo.for_guild(
                session, interaction.guild.id, enabled_only=False
            )
            if altar_row is None:
                await interaction.response.send_message(
                    "No altar configured.", ephemeral=True
                )
                return
            altar_id = altar_row.id
            await session.delete(altar_row)
            await audit_repo.append(
                session,
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                action="altar_removed",
                payload={"altar_id": altar_id},
            )
        await interaction.response.send_message(
            "Altar removed.", ephemeral=True
        )

    @altar.command(name="show", description="Show this server's altar.")
    @requires_admin()
    async def altar_show(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        async with self.bot.db() as session:
            a = await altars_repo.for_guild(
                session, interaction.guild.id, enabled_only=False
            )
        if a is None:
            await interaction.response.send_message(
                "No altar configured. Use `/stank-admin altar set`.",
                ephemeral=True,
            )
            return
        reaction_desc = a.display_name or "*(none)*"
        await interaction.response.send_message(
            f"**Altar:** <#{a.channel_id}>\n"
            f"- sticker pattern: `{a.sticker_name_pattern}`\n"
            f"- reaction emoji: {reaction_desc}\n"
            f"- enabled: {a.enabled}",
            ephemeral=True,
        )

    # ---- error handling --------------------------------------------------

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            msg = "You don't have permission to use this command."
        else:
            if isinstance(error, app_commands.TransformerError):
                raw = getattr(interaction, "data", None)
                resolved = (raw or {}).get("resolved", {}) if isinstance(raw, dict) else {}
                log.error(
                    "transformer error: value=%r value_type=%s target=%s resolved=%r",
                    error.value,
                    type(error.value).__name__,
                    getattr(error.transformer, "_error_display_name", "?"),
                    resolved,
                )
            log.exception("admin command error", exc_info=error)
            msg = f"Command failed: `{type(error).__name__}`."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: StankBot) -> None:
    await bot.add_cog(StankAdmin(bot))
