"""Mock event bridge — inject fake stanks/breaks/reactions without Discord.

All events flow through the real ChainService so the event log, derived
totals, and WebSocket broadcasts stay consistent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stankbot.db.engine import session_scope
from stankbot.db.models import Altar
from stankbot.db.repositories import altars as altars_repo
from stankbot.db.repositories import guilds as guilds_repo
from stankbot.db.repositories import players as players_repo
from stankbot.services.chain_service import ChainOutcome, ChainService, StankInput
from stankbot.services.session_service import SessionService
from stankbot.services.settings_service import SettingsService

log = logging.getLogger(__name__)

_DEFAULT_FAKE_USERS = [
    (1001, "Alice"),
    (1002, "Bob"),
    (1003, "Charlie"),
    (1004, "Diana"),
    (1005, "Eve"),
]


class MockEventBridge:
    """Framework-agnostic injector for dev-mode events."""

    def __init__(self, session_factory: async_sessionmaker, config) -> None:
        self.session_factory = session_factory
        self.config = config
        import random
        self._last_message_id = random.randint(10**12, 10**13)

    def _next_message_id(self) -> int:
        self._last_message_id += 1
        return self._last_message_id

    # ---- seeding ----------------------------------------------------------

    async def ensure_guild(self, guild_id: int | None = None) -> int:
        """Create the mock guild + altar + fake players if missing."""
        guild_id = guild_id or self.config.mock_default_guild_id or self.config.default_guild_id
        async with session_scope(self.session_factory) as session:
            await guilds_repo.ensure(session, guild_id, self.config.mock_default_guild_name)
            altar = await altars_repo.for_guild(session, guild_id, enabled_only=False)
            if altar is None:
                altar = Altar(
                    guild_id=guild_id,
                    channel_id=1,
                    sticker_name_pattern="stank",
                    reaction_emoji_name="✅",
                    enabled=True,
                )
                session.add(altar)
                await session.flush()
                log.info("Created mock altar for guild=%d", guild_id)
            for user_id, name in _DEFAULT_FAKE_USERS:
                await players_repo.get_or_create(session, guild_id, user_id, name)
        return guild_id

    async def _get_altar(self, session: AsyncSession, guild_id: int) -> Altar:
        altar = await altars_repo.for_guild(session, guild_id)
        if altar is None:
            raise RuntimeError(f"No altar configured for guild {guild_id}")
        return altar

    # ---- injection --------------------------------------------------------

    async def inject_stank(
        self,
        guild_id: int,
        user_id: int,
        display_name: str,
    ) -> dict:
        """Inject a valid stank and return the ChainResult fields."""
        async with session_scope(self.session_factory) as session:
            altar = await self._get_altar(session, guild_id)
            await players_repo.get_or_create(session, guild_id, user_id, display_name)

            settings = SettingsService(session)
            scoring = await settings.effective_scoring(guild_id, altar)
            session_svc = SessionService(session)
            await session_svc.ensure_started(guild_id, when=datetime.now(tz=UTC))

            stank_input = StankInput(
                guild_id=guild_id,
                altar=altar,
                message_id=self._next_message_id(),
                author_id=user_id,
                author_display_name=display_name,
                is_stank=True,
                created_at=datetime.now(tz=UTC),
            )
            chain_svc = ChainService(session, session_id_provider=session_svc)
            result = await chain_svc.process(stank_input, scoring)

        self._notify(guild_id, result)
        return {
            "outcome": result.outcome,
            "chain_length": result.chain_length,
            "chain_unique": result.chain_unique,
            "sp_awarded": result.sp_awarded,
            "message_id": stank_input.message_id,
        }

    async def inject_break(
        self,
        guild_id: int,
        user_id: int,
        display_name: str,
    ) -> dict:
        """Inject a chain-break message."""
        async with session_scope(self.session_factory) as session:
            altar = await self._get_altar(session, guild_id)
            await players_repo.get_or_create(session, guild_id, user_id, display_name)

            settings = SettingsService(session)
            scoring = await settings.effective_scoring(guild_id, altar)
            session_svc = SessionService(session)

            stank_input = StankInput(
                guild_id=guild_id,
                altar=altar,
                message_id=self._next_message_id(),
                author_id=user_id,
                author_display_name=display_name,
                is_stank=False,
                created_at=datetime.now(tz=UTC),
            )
            chain_svc = ChainService(session, session_id_provider=session_svc)
            result = await chain_svc.process(stank_input, scoring)

        self._notify(guild_id, result)
        return {
            "outcome": result.outcome,
            "broken_length": result.broken_length,
            "pp_awarded": result.pp_awarded,
            "sp_awarded": result.sp_awarded,
        }

    async def inject_reaction(
        self,
        guild_id: int,
        message_id: int,
        user_id: int,
        sticker_id: int = 1,
    ) -> dict:
        """Award a reaction bonus if the message is in an active chain."""
        async with session_scope(self.session_factory) as session:
            altar = await self._get_altar(session, guild_id)
            settings = SettingsService(session)
            scoring = await settings.effective_scoring(guild_id, altar)
            from stankbot.db.repositories import chains as chains_repo
            session_svc = SessionService(session)
            chain_svc = ChainService(session, session_id_provider=session_svc)
            current_chain = await chains_repo.current_chain(session, guild_id, altar.id)
            sp = await chain_svc.award_reaction_bonus(
                guild_id=guild_id,
                altar=altar,
                message_id=message_id,
                user_id=user_id,
                sticker_id=sticker_id,
                config=scoring,
                chain_id=current_chain.id if current_chain else None,
            )

        if sp > 0:
            import asyncio

            from stankbot.web.ws import broadcast_rank_update
            asyncio.create_task(broadcast_rank_update(self.session_factory, guild_id))

        return {"sp_awarded": sp}

    async def inject_noise(
        self,
        guild_id: int,
        user_id: int,
        display_name: str,
    ) -> dict:
        """Inject a non-stank message. If no chain is active this is a no-op."""
        return await self.inject_break(guild_id, user_id, display_name)

    # ---- notifications ----------------------------------------------------

    def _notify(self, guild_id: int, result) -> None:
        """Fire WebSocket broadcasts after the DB transaction commits."""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        from stankbot.web.ws import broadcast_rank_update, notify_chain_update

        if result.outcome == ChainOutcome.VALID_STANK:
            asyncio.create_task(
                notify_chain_update(
                    guild_id,
                    result.chain_length,
                    result.chain_unique,
                    None,
                )
            )
            asyncio.create_task(broadcast_rank_update(self.session_factory, guild_id))
        elif result.outcome == ChainOutcome.CHAIN_BREAK:
            asyncio.create_task(notify_chain_update(guild_id, 0, 0, None))
            asyncio.create_task(broadcast_rank_update(self.session_factory, guild_id))
