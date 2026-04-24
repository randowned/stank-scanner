"""``/preview`` — admin-only embed preview command.

This is the only admin slash command kept in Discord. All other admin
functionality is on the web dashboard at /admin/*.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from stankbot.cogs._checks import requires_admin
from stankbot.db.repositories import altars as altars_repo
from stankbot.services import embed_builders

if __name__ == "__main__":
    pass


class PreviewOnly(commands.Cog, name="stank-preview"):
    """Admin-only preview — no other admin commands live here."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
                embed = await embed_builders.build_record_embed(
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
                    session=session,
                )
            elif value == "chain-break":
                embed = await embed_builders.build_chain_break_embed(
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
                    session=session,
                )
            elif value == "new-session":
                embed = await embed_builders.build_new_session_embed(
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
                    session=session,
                    guild_id=guild.id,
                )
            else:
                embed = await embed_builders.build_cooldown_embed(
                    target_display_name=display_name,
                    cooldown_remaining="3m 20s",
                    cooldown_total="20m",
                    altar_channel_id=altar_channel_id,
                    board_url=board_url,
                    session=session,
                    guild_id=guild.id,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            msg = "You don't have permission to use this command."
        else:
            msg = f"Command failed: `{type(error).__name__}`."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PreviewOnly(bot))
