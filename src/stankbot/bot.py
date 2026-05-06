from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stankbot.config import AppConfig
from stankbot.db.engine import build_engine, build_sessionmaker, session_scope
from stankbot.scheduling.media_metrics_scheduler import MediaMetricsScheduler
from stankbot.scheduling.session_scheduler import SessionScheduler
from stankbot.services.media_providers import (
    MediaProviderRegistry,
    SpotifyProvider,
    YouTubeProvider,
)

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
    "stankbot.cogs.preview",
    "stankbot.cogs.media_commands",
)


class StankBot(commands.Bot):
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    _bot_guilds: list[dict[str, object]]
    _guilds_loaded: asyncio.Event

    def __init__(self, config: AppConfig) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=build_intents(),
            application_id=config.discord_app_id,
            chunk_guilds_at_startup=False,
        )
        self.config = config
        self.engine = build_engine(config.database_url)
        self.session_factory = build_sessionmaker(self.engine)
        self.scheduler = SessionScheduler(self)

        yt_key = config.youtube_api_key.get_secret_value() if config.youtube_api_key else None
        spot_id = config.spotify_client_id.get_secret_value() if config.spotify_client_id else None
        spot_secret = config.spotify_client_secret.get_secret_value() if config.spotify_client_secret else None

        self.media_registry = MediaProviderRegistry()
        self.media_registry.register(YouTubeProvider(api_key=yt_key))
        self.media_registry.register(SpotifyProvider(client_id=spot_id, client_secret=spot_secret))
        self.media_scheduler = MediaMetricsScheduler(self, self.media_registry)

        self._bot_guilds = []
        self._guilds_loaded = asyncio.Event()

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
        await self.media_scheduler.start()

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
        await self._load_bot_guilds()

    async def _load_bot_guilds(self) -> None:
        """Cache the list of guilds this bot is added to, for the web
        dashboard guild selector and owner super-admin access.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://discord.com/api/v10/users/@me/guilds",
                    headers={
                        "Authorization": f"Bot {self.config.discord_token.get_secret_value()}",
                    },
                )
            if resp.status_code != 200:
                log.warning("failed to fetch bot guilds: %s", resp.status_code)
                self._bot_guilds = []
            else:
                guilds_data: list[dict[str, object]] = resp.json()
                self._bot_guilds.clear()
                self._bot_guilds.extend(
                    {
                        "id": int(g["id"]),
                        "name": str(g.get("name", "")),
                        "icon": g.get("icon"),
                    }
                    for g in guilds_data
                )
                log.info("Loaded %d bot guilds", len(self._bot_guilds))
        except Exception:
            log.exception("error loading bot guilds")
            self._bot_guilds.clear()
        finally:
            self._guilds_loaded.set()

    async def close(self) -> None:
        await self.scheduler.shutdown()
        await self.media_scheduler.shutdown()
        await super().close()
        await self.engine.dispose()
        await self.media_registry.close()
