from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stankbot.config import AppConfig
from stankbot.db.engine import build_engine, build_sessionmaker, session_scope
from stankbot.scheduling.session_scheduler import SessionScheduler

log = logging.getLogger(__name__)


def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    intents.messages = True
    intents.reactions = True
    return intents


# Cogs loaded at startup. The /stank subcommands all live in one
# ``stank_commands`` GroupCog because discord.py binds a slash-command
# group to a single class; splitting board/points/cooldown/help across
# files would fight the framework. The message-event listener is
# independent and stays in its own cog.
_COG_MODULES: tuple[str, ...] = (
    "stankbot.cogs.chain_listener",
    "stankbot.cogs.stank_commands",
    "stankbot.cogs.admin",
)


class StankBot(commands.Bot):
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    def __init__(self, config: AppConfig) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=build_intents(),
            application_id=config.discord_app_id,
        )
        self.config = config
        self.engine = build_engine(config.database_url)
        self.session_factory = build_sessionmaker(self.engine)
        self.scheduler = SessionScheduler(self)

    @asynccontextmanager
    async def db(self) -> AsyncIterator[AsyncSession]:
        """Open a transactional session scope. Commits on clean exit,
        rolls back on exception.
        """
        async with session_scope(self.session_factory) as session:
            yield session

    async def send_embed_to(self, channel_id: int, embed: discord.Embed) -> None:
        """``EmbedSender`` implementation — used by the scheduler/announcer."""
        channel = self.get_channel(channel_id)
        if channel is None:
            channel = await self.fetch_channel(channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(embed=embed)
        else:
            log.warning(
                "send_embed_to: channel %d is not text-capable", channel_id
            )

    async def setup_hook(self) -> None:
        for module in _COG_MODULES:
            await self.load_extension(module)
        log.info("Loaded %d cogs", len(_COG_MODULES))

        await self.scheduler.start()

        if self.config.guild_ids:
            for gid in self.config.guild_ids:
                guild = discord.Object(id=gid)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            log.info("Synced slash commands to %d guild(s)", len(self.config.guild_ids))
        else:
            await self.tree.sync()
            log.info("Synced slash commands globally (may take up to 1 hour to propagate)")

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (id=%d)", self.user, self.user.id)

    async def close(self) -> None:
        await self.scheduler.shutdown()
        await super().close()
        await self.engine.dispose()
