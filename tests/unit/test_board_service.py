"""Board service — ``build_board_state`` record field population."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from stankbot.db.models import Altar, Guild, SessionEndReason
from stankbot.services.board_service import build_board_state
from stankbot.services.chain_service import ChainService, StankInput
from stankbot.services.scoring_service import ScoringConfig
from stankbot.services.session_service import SessionService


@pytest.fixture
async def env(session):  # type: ignore[no-untyped-def]
    """Guild + altar + active session + chain service."""
    guild = Guild(id=100, name="Test Guild")
    session.add(guild)
    await session.flush()
    altar = Altar(
        guild_id=100,
        channel_id=200,
        sticker_id=300,
        display_name="primary",
    )
    session.add(altar)
    await session.flush()
    sess_svc = SessionService(session=session)
    await sess_svc.ensure_started(100)
    chain_svc = ChainService(session=session, session_id_provider=sess_svc)
    return session, guild, altar, chain_svc


@pytest.fixture
def cfg() -> ScoringConfig:
    return ScoringConfig()


# ---------------------------------------------------------------------------
# Board state record fields
# ---------------------------------------------------------------------------


async def test_board_state_zero_records_with_no_chains(env) -> None:  # type: ignore[no-untyped-def]
    session, guild, altar, _ = env
    state = await build_board_state(
        session,
        guild_id=guild.id,
        guild_name=guild.name,
        altar=altar,
    )
    assert state.record == 0
    assert state.record_unique == 0
    assert state.alltime_record == 0
    assert state.alltime_record_unique == 0


async def test_board_state_reflects_session_record_after_chain_break(
    env, cfg
) -> None:  # type: ignore[no-untyped-def]
    session, guild, altar, chain_svc = env

    # Build and break a chain of 3
    await _build_and_break_chain(session, guild, altar, chain_svc, cfg, length=3)

    state = await build_board_state(
        session,
        guild_id=guild.id,
        guild_name=guild.name,
        altar=altar,
    )
    assert state.record == 3
    assert state.alltime_record == 3  # first chain ever = both records


async def test_board_state_session_record_zero_after_rollover_with_no_new_chain(
    env, cfg
) -> None:  # type: ignore[no-untyped-def]
    session, guild, altar, chain_svc = env

    # Session 1: chain of 4
    await _build_and_break_chain(
        session, guild, altar, chain_svc, cfg, length=4, base_msg_id=100,
    )

    # Roll the session
    sess_svc = SessionService(session=session)
    await sess_svc.end_session(
        guild.id, reason=SessionEndReason.AUTO, open_new=True,
    )

    state = await build_board_state(
        session,
        guild_id=guild.id,
        guild_name=guild.name,
        altar=altar,
    )
    assert state.record == 0  # reset!
    assert state.record_unique == 0
    assert state.alltime_record == 4  # persisted
    assert state.alltime_record_unique == 4


async def test_board_state_alltime_record_persists_after_rollover_with_new_chain(
    env, cfg
) -> None:  # type: ignore[no-untyped-def]
    session, guild, altar, chain_svc = env

    # Session 1: chain of 6
    await _build_and_break_chain(
        session, guild, altar, chain_svc, cfg, length=6, base_msg_id=100,
    )

    # Roll the session
    sess_svc = SessionService(session=session)
    await sess_svc.end_session(
        guild.id, reason=SessionEndReason.AUTO, open_new=True,
    )

    # Session 2: chain of 2 (doesn't beat any record)
    await _build_and_break_chain(
        session, guild, altar, chain_svc, cfg, length=2,
        base_msg_id=200,
        start_time=datetime(2026, 4, 19, 14, 0, tzinfo=UTC),
    )

    state = await build_board_state(
        session,
        guild_id=guild.id,
        guild_name=guild.name,
        altar=altar,
    )
    assert state.record == 2  # session 2 record
    assert state.record_unique == 2
    assert state.alltime_record == 6  # session 1 record still alltime best
    assert state.alltime_record_unique == 6


async def test_board_state_alltime_beats_session_after_rollover(
    env, cfg
) -> None:  # type: ignore[no-untyped-def]
    session, guild, altar, chain_svc = env

    # Session 1: chain of 3
    await _build_and_break_chain(
        session, guild, altar, chain_svc, cfg, length=3, base_msg_id=100,
    )

    # Roll
    sess_svc = SessionService(session=session)
    await sess_svc.end_session(
        guild.id, reason=SessionEndReason.AUTO, open_new=True,
    )

    # Session 2: chain of 8 (beats alltime!)
    await _build_and_break_chain(
        session, guild, altar, chain_svc, cfg, length=8,
        base_msg_id=200,
        start_time=datetime(2026, 4, 19, 14, 0, tzinfo=UTC),
    )

    state = await build_board_state(
        session,
        guild_id=guild.id,
        guild_name=guild.name,
        altar=altar,
    )
    assert state.record == 8  # fresh session record
    assert state.record_unique == 8
    assert state.alltime_record == 8  # alltime also updated
    assert state.alltime_record_unique == 8


async def test_board_state_handles_missing_records_gracefully(
    session,
) -> None:  # type: ignore[no-untyped-def]
    """Board state returns 0 for record fields when records table is empty."""
    guild = Guild(id=888, name="New Guild")
    session.add(guild)
    await session.flush()
    altar = Altar(guild_id=888, channel_id=1, sticker_id=1, display_name="primary")
    session.add(altar)
    await session.flush()
    sess_svc = SessionService(session=session)
    await sess_svc.ensure_started(888)

    state = await build_board_state(
        session, guild_id=888, guild_name="New Guild", altar=altar,
    )
    assert state.record == 0
    assert state.record_unique == 0
    assert state.alltime_record == 0
    assert state.alltime_record_unique == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_and_break_chain(
    session,  # type: ignore[no-untyped-def]
    guild,
    altar,
    chain_svc,
    cfg: ScoringConfig,
    *,
    length: int,
    base_msg_id: int = 100,
    start_time: datetime | None = None,
):
    t = start_time or datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
    # Cooldown is 1200s (20 min) — stagger by 21 min to avoid cooldown
    cooldown_pad = (cfg.cooldown_seconds or 1200) + 60

    for i in range(length):
        uid = 500 + i
        await chain_svc.process(
            StankInput(
                guild_id=guild.id,
                altar=altar,
                message_id=base_msg_id + i,
                author_id=uid,
                author_display_name=f"u{uid}",
                is_stank=True,
                created_at=t + timedelta(seconds=i * cooldown_pad),
            ),
            cfg,
        )

    breaker_id = 500 + length
    await chain_svc.process(
        StankInput(
            guild_id=guild.id,
            altar=altar,
            message_id=base_msg_id + 999,
            author_id=breaker_id,
            author_display_name=f"breaker{breaker_id}",
            is_stank=False,
            created_at=t + timedelta(seconds=length * cooldown_pad + 1),
        ),
        cfg,
    )
