"""ChainService — framework-agnostic core.

Accepts a ``StankInput`` describing an altar channel message, decides
whether it's a valid stank / cooldown violation / chain break / noise,
updates persistent state accordingly, and emits the correct events.

Invariants:
    * Every mutation goes through the event log.
    * Chain identity is persisted: each active chain has a ``Chain`` row
      with rows in ``chain_messages``.
    * Cooldowns are per (guild, altar, user).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Altar, Chain, EventType, RecordScope
from stankbot.db.repositories import (
    chains as chains_repo,
)
from stankbot.db.repositories import (
    cooldowns as cooldowns_repo,
)
from stankbot.db.repositories import (
    events as events_repo,
)
from stankbot.db.repositories import (
    players as players_repo,
)
from stankbot.db.repositories import (
    reaction_awards as reaction_repo,
)
from stankbot.db.repositories import (
    records as records_repo,
)
from stankbot.services import achievements as achievements_svc
from stankbot.services import scoring_service
from stankbot.services.scoring_service import ScoringConfig


class ChainOutcome(StrEnum):
    VALID_STANK = "valid_stank"
    COOLDOWN = "cooldown"
    CHAIN_BREAK = "chain_break"
    NOISE = "noise"  # non-stank message in a channel with no active chain
    DUPLICATE = "duplicate"  # Discord re-dispatch


@dataclass(slots=True)
class StankInput:
    """What the cog hands to ChainService for each altar-channel message."""

    guild_id: int
    altar: Altar
    message_id: int
    author_id: int
    author_display_name: str
    is_stank: bool  # cog determined whether the message content = the sticker
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass(slots=True)
class ChainResult:
    """What the cog gets back so it can react / announce / log."""

    outcome: ChainOutcome
    # SP/PP awarded on this message (sum of sub-events).
    sp_awarded: int = 0
    pp_awarded: int = 0
    # When outcome=VALID_STANK: the new chain length and unique count.
    chain_length: int = 0
    chain_unique: int = 0
    # When outcome=COOLDOWN: seconds remaining.
    cooldown_seconds_remaining: int = 0
    # When outcome=CHAIN_BREAK: the length of the broken chain.
    broken_length: int = 0
    finish_bonus_user_id: int | None = None
    # Whether a record was set as a result of this message.
    record_broken: bool = False
    alltime_record_broken: bool = False


@dataclass(slots=True)
class ChainService:
    session: AsyncSession
    session_id_provider: SessionIdProvider

    async def process(
        self, msg: StankInput, config: ScoringConfig
    ) -> ChainResult:
        await players_repo.get_or_create(
            self.session, msg.guild_id, msg.author_id, msg.author_display_name
        )
        await players_repo.touch_last_seen(
            self.session, msg.guild_id, msg.author_id, when=msg.created_at
        )

        current: Chain | None = await chains_repo.current_chain(
            self.session, msg.guild_id, msg.altar.id
        )

        if msg.is_stank:
            return await self._handle_stank(msg, config, current)
        if current is not None and (current.final_length is None):
            # Non-stank message while a chain is alive → chain break.
            return await self._handle_break(msg, config, current)
        return ChainResult(outcome=ChainOutcome.NOISE)

    # ---- internal handlers ------------------------------------------------

    async def _handle_stank(
        self, msg: StankInput, config: ScoringConfig, current: Chain | None
    ) -> ChainResult:
        # Cooldown check (per (guild, altar, user)).
        last = await cooldowns_repo.get_last_stank(
            self.session,
            guild_id=msg.guild_id,
            altar_id=msg.altar.id,
            user_id=msg.author_id,
        )
        remaining = cooldowns_repo.seconds_remaining(
            last, cooldown_seconds=config.cooldown_seconds, now=msg.created_at
        )
        if remaining > 0:
            return ChainResult(
                outcome=ChainOutcome.COOLDOWN,
                cooldown_seconds_remaining=remaining,
            )

        session_id = await self.session_id_provider.current(msg.guild_id)

        # Start a new chain or extend the live one.
        if current is None:
            current = await chains_repo.start_chain(
                self.session,
                guild_id=msg.guild_id,
                altar_id=msg.altar.id,
                starter_user_id=msg.author_id,
                session_id=session_id,
                started_at=msg.created_at,
            )
            await events_repo.append(
                self.session,
                guild_id=msg.guild_id,
                type=EventType.CHAIN_START,
                user_id=msg.author_id,
                altar_id=msg.altar.id,
                session_id=session_id,
                chain_id=current.id,
                message_id=msg.message_id,
                custom_event_key=msg.altar.custom_event_key,
                created_at=msg.created_at,
            )

        # Compute position and record the message.
        length, _ = await chains_repo.chain_length_and_unique(
            self.session, current.id
        )
        position = length + 1
        await chains_repo.append_message(
            self.session,
            chain_id=current.id,
            message_id=msg.message_id,
            user_id=msg.author_id,
            position=position,
            created_at=msg.created_at,
        )
        await cooldowns_repo.set_last_stank(
            self.session,
            guild_id=msg.guild_id,
            altar_id=msg.altar.id,
            user_id=msg.author_id,
            when=msg.created_at,
        )

        # Emit scoring events (split so history slices cleanly).
        sp_awarded = 0
        await events_repo.append(
            self.session,
            guild_id=msg.guild_id,
            type=EventType.SP_BASE,
            delta=config.sp_flat,
            user_id=msg.author_id,
            altar_id=msg.altar.id,
            session_id=session_id,
            chain_id=current.id,
            message_id=msg.message_id,
            custom_event_key=msg.altar.custom_event_key,
            reason="valid stank",
            created_at=msg.created_at,
        )
        sp_awarded += config.sp_flat

        if position > 1 and config.sp_position_bonus > 0:
            bonus = (position - 1) * config.sp_position_bonus
            await events_repo.append(
                self.session,
                guild_id=msg.guild_id,
                type=EventType.SP_POSITION_BONUS,
                delta=bonus,
                user_id=msg.author_id,
                altar_id=msg.altar.id,
                session_id=session_id,
                chain_id=current.id,
                message_id=msg.message_id,
                custom_event_key=msg.altar.custom_event_key,
                reason=f"position {position}",
                created_at=msg.created_at,
            )
            sp_awarded += bonus

        if position == 1:
            await events_repo.append(
                self.session,
                guild_id=msg.guild_id,
                type=EventType.SP_STARTER_BONUS,
                delta=config.sp_starter_bonus,
                user_id=msg.author_id,
                altar_id=msg.altar.id,
                session_id=session_id,
                chain_id=current.id,
                message_id=msg.message_id,
                custom_event_key=msg.altar.custom_event_key,
                reason="chain starter",
                created_at=msg.created_at,
            )
            sp_awarded += config.sp_starter_bonus

        new_length, new_unique = await chains_repo.chain_length_and_unique(
            self.session, current.id
        )
        await achievements_svc.evaluate_for_user(
            self.session,
            guild_id=msg.guild_id,
            user_id=msg.author_id,
            session_id=session_id,
            chain_id=current.id,
        )
        return ChainResult(
            outcome=ChainOutcome.VALID_STANK,
            sp_awarded=sp_awarded,
            chain_length=new_length,
            chain_unique=new_unique,
        )

    async def _handle_break(
        self, msg: StankInput, config: ScoringConfig, current: Chain
    ) -> ChainResult:
        session_id = await self.session_id_provider.current(msg.guild_id)
        contributors = await chains_repo.contributors(self.session, current.id)
        length = len(contributors)
        unique_count = len(set(contributors))

        # Finish bonus (to last non-breaker contributor).
        finish_recipient = scoring_service.finish_bonus_recipient(
            contributors, msg.author_id
        )
        sp_awarded = 0
        if finish_recipient is not None:
            await events_repo.append(
                self.session,
                guild_id=msg.guild_id,
                type=EventType.SP_FINISH_BONUS,
                delta=config.sp_finish_bonus,
                user_id=finish_recipient,
                altar_id=msg.altar.id,
                session_id=session_id,
                chain_id=current.id,
                message_id=msg.message_id,
                custom_event_key=msg.altar.custom_event_key,
                reason="chain finish",
                created_at=msg.created_at,
            )
            sp_awarded = config.sp_finish_bonus

        # Break penalty.
        pp = scoring_service.break_pp(length, config)
        await events_repo.append(
            self.session,
            guild_id=msg.guild_id,
            type=EventType.PP_BREAK,
            delta=pp,
            user_id=msg.author_id,
            altar_id=msg.altar.id,
            session_id=session_id,
            chain_id=current.id,
            message_id=msg.message_id,
            custom_event_key=msg.altar.custom_event_key,
            reason=f"broke chain of {length}",
            created_at=msg.created_at,
        )

        await chains_repo.break_chain(
            self.session,
            current,
            broken_by_user_id=msg.author_id,
            broken_at=msg.created_at,
        )
        await cooldowns_repo.clear_for_altar(
            self.session, guild_id=msg.guild_id, altar_id=msg.altar.id
        )
        await events_repo.append(
            self.session,
            guild_id=msg.guild_id,
            type=EventType.CHAIN_BREAK,
            user_id=msg.author_id,
            altar_id=msg.altar.id,
            session_id=session_id,
            chain_id=current.id,
            message_id=msg.message_id,
            custom_event_key=msg.altar.custom_event_key,
            created_at=msg.created_at,
        )

        # Record check.
        record_broken, alltime_broken = await self._check_records(
            guild_id=msg.guild_id,
            altar_id=msg.altar.id,
            chain_id=current.id,
            session_id=session_id,
            length=length,
            unique_count=unique_count,
            when=msg.created_at,
        )

        await achievements_svc.evaluate_for_user(
            self.session,
            guild_id=msg.guild_id,
            user_id=msg.author_id,
            session_id=session_id,
            chain_id=current.id,
        )
        if finish_recipient is not None and finish_recipient != msg.author_id:
            await achievements_svc.evaluate_for_user(
                self.session,
                guild_id=msg.guild_id,
                user_id=finish_recipient,
                session_id=session_id,
                chain_id=current.id,
            )
        return ChainResult(
            outcome=ChainOutcome.CHAIN_BREAK,
            sp_awarded=sp_awarded,
            pp_awarded=pp,
            broken_length=length,
            chain_unique=unique_count,
            finish_bonus_user_id=finish_recipient,
            record_broken=record_broken,
            alltime_record_broken=alltime_broken,
        )

    async def _check_records(
        self,
        *,
        guild_id: int,
        altar_id: int,
        chain_id: int,
        session_id: int | None,
        length: int,
        unique_count: int,
        when: datetime,
    ) -> tuple[bool, bool]:
        session_rec = await records_repo.get(
            self.session,
            guild_id=guild_id,
            altar_id=altar_id,
            scope=RecordScope.SESSION,
        )
        session_beat = session_rec is None or records_repo.beats(
            length,
            unique_count,
            session_rec.chain_length,
            session_rec.unique_count,
        )
        if session_beat:
            await records_repo.upsert(
                self.session,
                guild_id=guild_id,
                altar_id=altar_id,
                scope=RecordScope.SESSION,
                chain_length=length,
                unique_count=unique_count,
                chain_id=chain_id,
                session_id=session_id,
                set_at=when,
            )

        alltime_rec = await records_repo.get(
            self.session,
            guild_id=guild_id,
            altar_id=altar_id,
            scope=RecordScope.ALLTIME,
        )
        alltime_beat = alltime_rec is None or records_repo.beats(
            length,
            unique_count,
            alltime_rec.chain_length,
            alltime_rec.unique_count,
        )
        if alltime_beat:
            await records_repo.upsert(
                self.session,
                guild_id=guild_id,
                altar_id=altar_id,
                scope=RecordScope.ALLTIME,
                chain_length=length,
                unique_count=unique_count,
                chain_id=chain_id,
                session_id=session_id,
                set_at=when,
            )
        return session_beat, alltime_beat

    # ---- reactions --------------------------------------------------------

    async def award_reaction_bonus(
        self,
        *,
        guild_id: int,
        altar: Altar,
        message_id: int,
        user_id: int,
        sticker_id: int,
        config: ScoringConfig,
        chain_id: int | None = None,
        created_at: datetime | None = None,
        user_display_name: str | None = None,
    ) -> int:
        """Idempotent reaction SP. Returns the amount awarded (0 if this
        (message, user, sticker) was already claimed, or the bonus is off).
        """
        if config.sp_reaction <= 0:
            return 0
        if not await chains_repo.message_in_active_chain(
            self.session, guild_id, altar.id, message_id
        ):
            return 0
        await players_repo.get_or_create(
            self.session, guild_id, user_id, user_display_name
        )
        claimed = await reaction_repo.try_claim(
            self.session,
            guild_id=guild_id,
            message_id=message_id,
            user_id=user_id,
            sticker_id=sticker_id,
            chain_id=chain_id,
        )
        if not claimed:
            return 0
        session_id = await self.session_id_provider.current(guild_id)
        await events_repo.append(
            self.session,
            guild_id=guild_id,
            type=EventType.SP_REACTION,
            delta=config.sp_reaction,
            user_id=user_id,
            altar_id=altar.id,
            session_id=session_id,
            chain_id=chain_id,
            message_id=message_id,
            custom_event_key=altar.custom_event_key,
            reason="stank reaction",
            created_at=created_at,
        )
        await achievements_svc.evaluate_for_user(
            self.session,
            guild_id=guild_id,
            user_id=user_id,
            session_id=session_id,
            chain_id=chain_id,
        )
        return config.sp_reaction


class SessionIdProvider:
    """Abstraction for "what's the current session_id for this guild?".

    Implemented by ``SessionService``; declared here as a small protocol-ish
    class so ``ChainService`` doesn't import ``SessionService`` (avoids the
    obvious circular import). Tests can pass a trivial stub.
    """

    async def current(self, guild_id: int) -> int | None:  # pragma: no cover - stub
        raise NotImplementedError
