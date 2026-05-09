"""Achievements — unit tests against in-memory SQLite.

Locks in behaviour for:
    * _streaker (3+ consecutive sessions with SP > 0)
    * _centurion (100+ stanks in a chain)
    * _comeback_kid (negative → positive net SP)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from stankbot.db.models import Altar, Chain, ChainMessage, EventType, Guild
from stankbot.db.repositories import events as events_repo
from stankbot.services.achievements import _centurion, _comeback_kid, _streaker

# ── helpers ────────────────────────────────────────────────────────────────


async def _event(
    session: Any,
    *,
    guild_id: int = 1,
    user_id: int,
    type: EventType | str,
    delta: int = 0,
    session_id: int | None = None,
    chain_id: int | None = None,
) -> None:
    await events_repo.append(
        session,
        guild_id=guild_id,
        type=type,
        delta=delta,
        user_id=user_id,
        session_id=session_id,
        chain_id=chain_id,
    )


async def _start_session(session: Any, guild_id: int = 1) -> int:
    ev = await events_repo.append(
        session, guild_id=guild_id, type=EventType.SESSION_START
    )
    return ev.id


async def _mk_guild_altar(session: Any, guild_id: int = 1) -> None:
    session.add(Guild(id=guild_id, name="Test"))
    await session.flush()
    session.add(Altar(guild_id=guild_id, channel_id=200, sticker_name_pattern="stank"))
    await session.flush()


async def _mk_chain(
    session: Any, guild_id: int = 1, altar_id: int = 1, starter_id: int = 100,
) -> Chain:
    chain = Chain(
        guild_id=guild_id,
        altar_id=altar_id,
        starter_user_id=starter_id,
        session_id=0,
        started_at=datetime.now(tz=UTC),
    )
    session.add(chain)
    await session.flush()
    return chain


# ── _streaker ──────────────────────────────────────────────────────────────


async def test_streaker_three_consecutive_sessions(session: Any) -> None:
    sid1 = await _start_session(session)
    sid2 = await _start_session(session)
    sid3 = await _start_session(session)

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid2)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid3)

    assert await _streaker(session, 1, 100) is True


async def test_streaker_not_enough_sessions(session: Any) -> None:
    sid1 = await _start_session(session)
    sid2 = await _start_session(session)

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid2)

    assert await _streaker(session, 1, 100) is False


async def test_streaker_gap_breaks_run(session: Any) -> None:
    sid1 = await _start_session(session)
    await _start_session(session)  # sid2 — no stank for user 100, creates gap
    sid3 = await _start_session(session)
    sid4 = await _start_session(session)

    # User stanked in sessions 1, 3, 4 — gap at 2 breaks the run
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    # sid2: no stank for user 100
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid3)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid4)

    assert await _streaker(session, 1, 100) is False


async def test_streaker_four_consecutive_returns_true(session: Any) -> None:
    sid1 = await _start_session(session)
    sid2 = await _start_session(session)
    sid3 = await _start_session(session)
    sid4 = await _start_session(session)

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid2)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid3)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid4)

    assert await _streaker(session, 1, 100) is True


async def test_streaker_zero_sessions_total(session: Any) -> None:
    assert await _streaker(session, 1, 100) is False


async def test_streaker_different_user_unaffected(session: Any) -> None:
    sid1 = await _start_session(session)
    sid2 = await _start_session(session)
    sid3 = await _start_session(session)

    await _event(session, user_id=200, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=10, session_id=sid2)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=10, session_id=sid3)

    # User 100 did nothing — should not be a streaker
    assert await _streaker(session, 1, 100) is False


# ── _centurion ──────────────────────────────────────────────────────────────


async def test_centurion_100_sp_events_in_single_chain(session: Any) -> None:
    await _mk_guild_altar(session)
    chain = await _mk_chain(session, starter_id=100)
    now = datetime.now(tz=UTC)

    for i in range(100):
        session.add(
            ChainMessage(
                chain_id=chain.id,
                message_id=i + 1,
                user_id=100,
                position=i + 1,
                created_at=now,
            )
        )
    await session.flush()

    assert await _centurion(session, 1, 100) is True


async def test_centurion_below_threshold(session: Any) -> None:
    await _mk_guild_altar(session)
    chain = await _mk_chain(session, starter_id=100)
    now = datetime.now(tz=UTC)

    for i in range(99):
        session.add(
            ChainMessage(
                chain_id=chain.id,
                message_id=i + 1,
                user_id=100,
                position=i + 1,
                created_at=now,
            )
        )
    await session.flush()

    assert await _centurion(session, 1, 100) is False


async def test_centurion_combined_across_chains_not_enough(session: Any) -> None:
    await _mk_guild_altar(session)
    now = datetime.now(tz=UTC)
    # 50 stanks in chain A + 50 in chain B ≠ 100 in one chain
    for chain_i in range(2):
        chain = await _mk_chain(session, starter_id=100)
        for i in range(50):
            session.add(
                ChainMessage(
                    chain_id=chain.id,
                    message_id=(chain_i * 1000) + i + 1,
                    user_id=100,
                    position=i + 1,
                    created_at=now,
                )
            )
    await session.flush()

    assert await _centurion(session, 1, 100) is False


async def test_centurion_user_in_100plus_chain_one_message(session: Any) -> None:
    """User contributed only 1 message but the chain itself reached 100."""
    await _mk_guild_altar(session)
    chain = await _mk_chain(session, starter_id=200)  # started by someone else
    now = datetime.now(tz=UTC)

    # User 100 has just 1 message in the chain.
    session.add(
        ChainMessage(
            chain_id=chain.id,
            message_id=1,
            user_id=100,
            position=1,
            created_at=now,
        )
    )
    # 99 more messages from other users fill out the chain to 100 total.
    for i in range(99):
        session.add(
            ChainMessage(
                chain_id=chain.id,
                message_id=i + 1000,
                user_id=300,  # different user
                position=i + 2,
                created_at=now,
            )
        )
    await session.flush()

    assert await _centurion(session, 1, 100) is True


# ── _comeback_kid ───────────────────────────────────────────────────────────


async def test_comeback_kid_was_negative_now_positive(session: Any) -> None:
    # Went -30 PP, then earned +50 SP → net = +20, and was negative at some point
    await _event(session, user_id=100, type=EventType.PP_BREAK, delta=30)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=50)

    assert await _comeback_kid(session, 1, 100) is True


async def test_comeback_kid_never_negative(session: Any) -> None:
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=20)

    assert await _comeback_kid(session, 1, 100) is False


async def test_comeback_kid_still_negative(session: Any) -> None:
    await _event(session, user_id=100, type=EventType.PP_BREAK, delta=50)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)

    assert await _comeback_kid(session, 1, 100) is False


async def test_comeback_kid_no_events_at_all(session: Any) -> None:
    assert await _comeback_kid(session, 1, 100) is False


async def test_comeback_kid_team_player_never_negative(session: Any) -> None:
    """Team Player SP then PP, net still positive, never actually negative."""
    await _event(session, user_id=100, type=EventType.SP_TEAM_PLAYER, delta=20)
    await _event(session, user_id=100, type=EventType.PP_BREAK, delta=15)

    # Net +5, but was never negative (team_player kept them in the green).
    assert await _comeback_kid(session, 1, 100) is False


async def test_comeback_kid_team_player_genuine_comeback(session: Any) -> None:
    """Team Player SP after being negative counts as a genuine comeback."""
    await _event(session, user_id=100, type=EventType.PP_BREAK, delta=30)
    await _event(session, user_id=100, type=EventType.SP_TEAM_PLAYER, delta=20)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=15)

    # Net +5, was negative after PP, then team_player + SP base recovered.
    assert await _comeback_kid(session, 1, 100) is True
