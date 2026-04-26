"""player_totals repository — unit tests against in-memory SQLite.

Covers:
    * upsert (new row, cumulative delta, idempotent)
    * get
    * rebuild (from events, all-time + per-session rows)
    * get_rank (rank 1, rank N, None for missing user)
    * startup warm pattern (rebuild when cache empty, skip when populated)
"""

from __future__ import annotations

from typing import Any

from stankbot.db.models import EventType, Guild, PlayerTotal
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import player_totals as pt_repo

# ── helpers ────────────────────────────────────────────────────────────────


async def _event(
    session: Any,
    *,
    guild_id: int = 1,
    user_id: int,
    type: EventType | str,
    delta: int = 0,
    session_id: int | None = None,
) -> None:
    await events_repo.append(
        session,
        guild_id=guild_id,
        type=type,
        delta=delta,
        user_id=user_id,
        session_id=session_id,
    )


async def _ensure_guild(session: Any, guild_id: int = 1) -> None:
    session.add(Guild(id=guild_id, name="Test"))
    await session.flush()


# ── upsert ─────────────────────────────────────────────────────────────────


async def test_upsert_creates_new_row(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=25)
    row = await pt_repo.get(session, 1, 100)
    assert row is not None
    assert row.earned_sp == 25
    assert row.punishments == 0


async def test_upsert_accumulates_deltas(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=10)
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=5, pp_delta=3)
    await pt_repo.upsert(session, guild_id=1, user_id=100, pp_delta=2)
    row = await pt_repo.get(session, 1, 100)
    assert row.earned_sp == 15
    assert row.punishments == 5


async def test_upsert_separates_users(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=10)
    await pt_repo.upsert(session, guild_id=1, user_id=200, sp_delta=30)
    row_a = await pt_repo.get(session, 1, 100)
    row_b = await pt_repo.get(session, 1, 200)
    assert row_a.earned_sp == 10
    assert row_b.earned_sp == 30


async def test_upsert_session_scoped_rows(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, session_id=5, sp_delta=10)
    await pt_repo.upsert(session, guild_id=1, user_id=100, session_id=0, sp_delta=20)
    sess_row = await pt_repo.get(session, 1, 100, session_id=5)
    all_row = await pt_repo.get(session, 1, 100, session_id=0)
    assert sess_row.earned_sp == 10
    assert all_row.earned_sp == 20


# ── get ────────────────────────────────────────────────────────────────────


async def test_get_returns_none_when_missing(session: Any) -> None:
    assert await pt_repo.get(session, 1, 999) is None


async def test_get_returns_row_when_present(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=42)
    row = await pt_repo.get(session, 1, 100)
    assert row is not None
    assert row.earned_sp == 42


# ── rebuild ────────────────────────────────────────────────────────────────


async def test_rebuild_empty_guild_returns_zero(session: Any) -> None:
    await _ensure_guild(session)
    count = await pt_repo.rebuild(session, 1)
    assert count == 0


async def test_rebuild_populates_all_time_rows(session: Any) -> None:
    await _ensure_guild(session)
    # Insert events through the raw repo (bypassing write-through) to simulate
    # the stale-cache scenario.
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, user_id=100, type=EventType.SP_STARTER_BONUS, delta=15)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=30)
    await _event(session, user_id=200, type=EventType.PP_BREAK, delta=25)
    await session.flush()

    count = await pt_repo.rebuild(session, 1)
    assert count == 2  # two users with all-time rows

    row_a = await pt_repo.get(session, 1, 100)
    row_b = await pt_repo.get(session, 1, 200)
    assert row_a.earned_sp == 25  # 10 + 15
    assert row_a.punishments == 0
    assert row_b.earned_sp == 30
    assert row_b.punishments == 25


async def test_rebuild_populates_per_session_rows(session: Any) -> None:
    await _ensure_guild(session)
    sid1 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id
    sid2 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=5, session_id=sid2)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=30, session_id=sid1)
    await session.flush()

    count = await pt_repo.rebuild(session, 1)
    # all-time: user 100 (15), user 200 (30) = 2
    # per-session: 100@sid1, 100@sid2, 200@sid1 = 3
    # total = 5
    assert count == 5

    # Verify per-session rows
    row = await pt_repo.get(session, 1, 100, session_id=sid1)
    assert row.earned_sp == 10
    row = await pt_repo.get(session, 1, 100, session_id=sid2)
    assert row.earned_sp == 5
    row = await pt_repo.get(session, 1, 200, session_id=sid1)
    assert row.earned_sp == 30


async def test_rebuild_replaces_existing_rows(session: Any) -> None:
    """Calling rebuild twice should produce the same result — not double-count."""
    await _ensure_guild(session)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await session.flush()

    await pt_repo.rebuild(session, 1)
    await pt_repo.rebuild(session, 1)  # second call

    row = await pt_repo.get(session, 1, 100)
    assert row.earned_sp == 10  # not 20


# ── get_rank ───────────────────────────────────────────────────────────────


async def test_get_rank_returns_none_when_no_cache_row(session: Any) -> None:
    assert await pt_repo.get_rank(session, 1, 999) is None


async def test_get_rank_top_earner_is_rank_1(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=50)
    await pt_repo.upsert(session, guild_id=1, user_id=200, sp_delta=10)
    assert await pt_repo.get_rank(session, 1, 100) == 1
    assert await pt_repo.get_rank(session, 1, 200) == 2


async def test_get_rank_ties_count_as_separate_ranks(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, sp_delta=50)
    await pt_repo.upsert(session, guild_id=1, user_id=200, sp_delta=50)
    # Both have net=50. Each sees the other as NOT strictly higher, so both are rank 1
    # (get_rank counts rows where net > self, so ties = same rank)
    rank_a = await pt_repo.get_rank(session, 1, 100)
    rank_b = await pt_repo.get_rank(session, 1, 200)
    assert rank_a == 1
    assert rank_b == 1


async def test_get_rank_respects_session_scoping(session: Any) -> None:
    await pt_repo.upsert(session, guild_id=1, user_id=100, session_id=0, sp_delta=10)
    await pt_repo.upsert(session, guild_id=1, user_id=200, session_id=0, sp_delta=50)
    await pt_repo.upsert(session, guild_id=1, user_id=100, session_id=5, sp_delta=30)
    await pt_repo.upsert(session, guild_id=1, user_id=200, session_id=5, sp_delta=10)
    # All-time: 100=10 rank 2, 200=50 rank 1
    # Session 5: 100=30 rank 1, 200=10 rank 2
    assert await pt_repo.get_rank(session, 1, 100, session_id=0) == 2
    assert await pt_repo.get_rank(session, 1, 200, session_id=0) == 1
    assert await pt_repo.get_rank(session, 1, 100, session_id=5) == 1
    assert await pt_repo.get_rank(session, 1, 200, session_id=5) == 2


# ── startup warm pattern ──────────────────────────────────────────────────


async def test_startup_warm_rebuilds_when_cache_empty_but_events_exist(session: Any) -> None:
    """Simulate the startup warm logic: cache is empty, events exist, rebuild
    populates the cache and leaderboard works."""
    from sqlalchemy import delete, func, select

    await _ensure_guild(session)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=30)
    await session.flush()

    # Delete all cache rows to simulate stale cache (write-through already ran)
    await session.execute(delete(PlayerTotal).where(PlayerTotal.guild_id == 1))
    await session.flush()

    # Now cache is empty but events exist — this is the startup warm scenario
    cached = await session.execute(
        select(func.count()).where(PlayerTotal.guild_id == 1)
    )
    assert cached.scalar_one() == 0  # cache is empty

    # Rebuild (simulating the warm logic)
    count = await pt_repo.rebuild(session, 1)
    assert count == 2  # two users

    # Now leaderboard should work via player_totals
    from stankbot.db.repositories.events import leaderboard

    rows = await leaderboard(session, 1)
    assert len(rows) == 2
    assert rows[0][0] == 200  # higher SP
    assert rows[1][0] == 100


async def test_startup_warm_skips_when_cache_populated(session: Any) -> None:
    """If cache already has rows, the warm should skip rebuilding."""
    from sqlalchemy import func, select

    await _ensure_guild(session)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10)
    await session.flush()

    # Cache should already be populated via write-through
    cached = await session.execute(
        select(func.count()).where(PlayerTotal.guild_id == 1)
    )
    assert cached.scalar_one() == 1  # write-through already ran

    # Running rebuild again shouldn't change the count (idempotent)
    count = await pt_repo.rebuild(session, 1)
    assert count == 1


async def test_startup_warm_empty_guild_without_events(session: Any) -> None:
    """No guild → no rebuild needed."""
    from sqlalchemy import func, select

    await _ensure_guild(session)
    # No events at all
    cached = await session.execute(
        select(func.count()).where(PlayerTotal.guild_id == 1)
    )
    assert cached.scalar_one() == 0
    count = await pt_repo.rebuild(session, 1)
    assert count == 0  # nothing to rebuild


# ── session counters (stanks_in_session, reactions_in_session) ─────────────


async def test_upsert_with_session_counters(session: Any) -> None:
    await pt_repo.upsert(
        session,
        guild_id=1,
        user_id=100,
        session_id=5,
        sp_delta=10,
        stanks_in_session_delta=2,
        reactions_in_session_delta=1,
    )
    row = await pt_repo.get(session, 1, 100, session_id=5)
    assert row.earned_sp == 10
    assert row.stanks_in_session == 2
    assert row.reactions_in_session == 1


async def test_upsert_accumulates_session_counters(session: Any) -> None:
    await pt_repo.upsert(
        session,
        guild_id=1,
        user_id=100,
        session_id=5,
        sp_delta=10,
        stanks_in_session_delta=2,
    )
    await pt_repo.upsert(
        session,
        guild_id=1,
        user_id=100,
        session_id=5,
        stanks_in_session_delta=3,
        reactions_in_session_delta=1,
    )
    row = await pt_repo.get(session, 1, 100, session_id=5)
    assert row.stanks_in_session == 5
    assert row.reactions_in_session == 1


async def test_rebuild_populates_session_counters(session: Any) -> None:
    await _ensure_guild(session)
    sid1 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id

    # SP_BASE awards 10, SP_REACTION awards 1
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=5, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_REACTION, delta=1, session_id=sid1)
    await _event(session, user_id=200, type=EventType.SP_BASE, delta=30, session_id=sid1)
    await session.flush()

    count = await pt_repo.rebuild(session, 1)
    assert count >= 2  # at least all-time + session rows

    row = await pt_repo.get(session, 1, 100, session_id=sid1)
    assert row.stanks_in_session == 2
    assert row.reactions_in_session == 1
    assert row.earned_sp == 16  # 10 + 5 + 1 (SP_REACTION also adds to earned_sp)

    row2 = await pt_repo.get(session, 1, 200, session_id=sid1)
    assert row2.stanks_in_session == 1
    assert row2.reactions_in_session == 0


async def test_rebuild_session_counters_separate_sessions(session: Any) -> None:
    await _ensure_guild(session)
    sid1 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id
    sid2 = (await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)).id

    await _event(session, user_id=100, type=EventType.SP_BASE, delta=10, session_id=sid1)
    await _event(session, user_id=100, type=EventType.SP_BASE, delta=5, session_id=sid2)
    await _event(session, user_id=100, type=EventType.SP_REACTION, delta=1, session_id=sid1)
    await session.flush()

    await pt_repo.rebuild(session, 1)

    row1 = await pt_repo.get(session, 1, 100, session_id=sid1)
    row2 = await pt_repo.get(session, 1, 100, session_id=sid2)

    assert row1.stanks_in_session == 1
    assert row1.reactions_in_session == 1
    assert row2.stanks_in_session == 1
    assert row2.reactions_in_session == 0
