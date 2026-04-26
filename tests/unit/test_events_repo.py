"""Events repository — unit tests against in-memory SQLite.

Locks in behaviour for:
    * append
    * sp_pp_totals (alltime, session-scoped, edge cases)
    * user_rank
    * leaderboard (order, limit/offset)
    * latest_session_start_id / session_event_ids
    * count_sp_base_per_user_for_session / _for_chain
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from stankbot.db.models import EventType
from stankbot.db.repositories import events as events_repo

# ── helpers ────────────────────────────────────────────────────────────────


async def _event(
    session: Any,
    *,
    guild_id: int,
    user_id: int,
    type: EventType | str,
    delta: int = 0,
    session_id: int | None = None,
    chain_id: int | None = None,
    altar_id: int | None = None,
    created_at: datetime | None = None,
) -> None:
    await events_repo.append(
        session,
        guild_id=guild_id,
        type=type,
        delta=delta,
        user_id=user_id,
        session_id=session_id,
        chain_id=chain_id,
        altar_id=altar_id,
        created_at=created_at,
    )


# ── append ─────────────────────────────────────────────────────────────────


async def test_append_flushes_and_returns_event(session: Any) -> None:
    ev = await events_repo.append(
        session,
        guild_id=1,
        type=EventType.SP_BASE,
        delta=10,
        user_id=100,
        session_id=5,
        chain_id=3,
        reason="test",
    )
    assert ev.id is not None
    assert ev.guild_id == 1
    assert ev.type == "sp_base"
    assert ev.delta == 10
    assert ev.user_id == 100
    assert ev.session_id == 5
    assert ev.chain_id == 3
    assert ev.reason == "test"


async def test_append_marker_event_zero_delta(session: Any) -> None:
    ev = await events_repo.append(
        session,
        guild_id=1,
        type=EventType.SESSION_START,
        delta=0,
        user_id=None,
    )
    assert ev.delta == 0
    assert ev.user_id is None


# ── sp_pp_totals ───────────────────────────────────────────────────────────


async def test_sp_pp_totals_alltime_sums_across_sessions(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=1)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=2)
    sp, pp = await events_repo.sp_pp_totals(session, 1, 100)
    assert sp == 20
    assert pp == 0


async def test_sp_pp_totals_session_scoped(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=10)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=5, session_id=20)
    sp, pp = await events_repo.sp_pp_totals(session, 1, 100, session_id=10)
    assert sp == 10
    assert pp == 0


async def test_sp_pp_totals_no_events_returns_zeros(session: Any) -> None:
    sp, pp = await events_repo.sp_pp_totals(session, 1, 999)
    assert sp == 0
    assert pp == 0


async def test_sp_pp_totals_only_sp_no_pp(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=25)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_STARTER_BONUS, delta=15)
    sp, pp = await events_repo.sp_pp_totals(session, 1, 100)
    assert sp == 40
    assert pp == 0


async def test_sp_pp_totals_mixed_sp_and_pp(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_FINISH_BONUS, delta=15)
    await _event(session, guild_id=1, user_id=100, type=EventType.PP_BREAK, delta=30)
    sp, pp = await events_repo.sp_pp_totals(session, 1, 100)
    assert sp == 25
    assert pp == 30


async def test_sp_pp_totals_all_sp_types_counted(session: Any) -> None:
    """Verify every SP event type is included in the sum."""
    sp_types = [
        (EventType.SP_BASE, 10),
        (EventType.SP_POSITION_BONUS, 2),
        (EventType.SP_STARTER_BONUS, 15),
        (EventType.SP_FINISH_BONUS, 15),
        (EventType.SP_REACTION, 1),
        (EventType.SP_TEAM_PLAYER, 20),
    ]
    for t, d in sp_types:
        await _event(session, guild_id=1, user_id=100, type=t, delta=d)
    sp, pp = await events_repo.sp_pp_totals(session, 1, 100)
    assert sp == 63


async def test_sp_pp_totals_session_scoped_only_pp(session: Any) -> None:
    await _event(session, guild_id=1, user_id=200, type=EventType.PP_BREAK, delta=50, session_id=5)
    sp, pp = await events_repo.sp_pp_totals(session, 1, 200, session_id=5)
    assert sp == 0
    assert pp == 50


async def test_sp_pp_totals_different_users_isolated(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=30)
    sp100, _ = await events_repo.sp_pp_totals(session, 1, 100)
    sp200, _ = await events_repo.sp_pp_totals(session, 1, 200)
    assert sp100 == 10
    assert sp200 == 30


# ── leaderboard ────────────────────────────────────────────────────────────


async def test_leaderboard_returns_correct_order_by_net_sp(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=50)
    await _event(session, guild_id=1, user_id=300, type=EventType.SP_BASE, delta=30)
    rows = await events_repo.leaderboard(session, 1)
    assert len(rows) == 3
    assert rows[0][0] == 200  # highest SP
    assert rows[1][0] == 300
    assert rows[2][0] == 100


async def test_leaderboard_net_sp_with_pp_penalty(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=50)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=50)
    await _event(session, guild_id=1, user_id=200, type=EventType.PP_BREAK, delta=30)
    rows = await events_repo.leaderboard(session, 1)
    # net: 100=50, 200=20 — so 100 ranks above 200
    assert rows[0][0] == 100
    assert rows[1][0] == 200


async def test_leaderboard_respects_limit(session: Any) -> None:
    for uid in (100, 200, 300, 400, 500):
        await _event(session, guild_id=1, user_id=uid, type=EventType.SP_BASE, delta=uid)
    rows = await events_repo.leaderboard(session, 1, limit=3)
    assert len(rows) == 3


async def test_leaderboard_respects_offset(session: Any) -> None:
    for uid in (100, 200, 300, 400, 500):
        await _event(session, guild_id=1, user_id=uid, type=EventType.SP_BASE, delta=uid)
    # user with highest delta first: 500, 400, 300, 200, 100
    rows = await events_repo.leaderboard(session, 1, offset=2, limit=2)
    assert len(rows) == 2
    assert rows[0][0] == 300
    assert rows[1][0] == 200


async def test_leaderboard_session_scoped(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=1)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=50, session_id=2)
    rows = await events_repo.leaderboard(session, 1, session_id=1)
    assert len(rows) == 1
    assert rows[0][0] == 100


async def test_leaderboard_empty_guild(session: Any) -> None:
    rows = await events_repo.leaderboard(session, 1)
    assert rows == []


# ── user_rank ──────────────────────────────────────────────────────────────


async def test_user_rank_returns_1_for_top_earner(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=50)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=10)
    rank = await events_repo.user_rank(session, 1, 100)
    assert rank == 1


async def test_user_rank_returns_none_for_user_without_events(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10)
    rank = await events_repo.user_rank(session, 1, 999)
    assert rank is None


async def test_user_rank_respects_session_scoping(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=1)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=50, session_id=2)
    # In session 1, 100 is rank 1; in all-time, 200 is rank 1
    assert await events_repo.user_rank(session, 1, 100, session_id=1) == 1
    assert await events_repo.user_rank(session, 1, 200) == 1
    assert await events_repo.user_rank(session, 1, 100) == 2


async def test_user_rank_correct_for_multiple_users(session: Any) -> None:
    for uid, delta in [(100, 50), (200, 30), (300, 60)]:
        await _event(session, guild_id=1, user_id=uid, type=EventType.SP_BASE, delta=delta)
    assert await events_repo.user_rank(session, 1, 300) == 1
    assert await events_repo.user_rank(session, 1, 100) == 2
    assert await events_repo.user_rank(session, 1, 200) == 3


# ── latest_session_start_id ────────────────────────────────────────────────


async def test_latest_session_start_id_none_when_no_session(session: Any) -> None:
    sid = await events_repo.latest_session_start_id(session, 1)
    assert sid is None


async def test_latest_session_start_id_returns_most_recent(session: Any) -> None:
    await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)
    ev2 = await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)
    sid = await events_repo.latest_session_start_id(session, 1)
    assert sid == ev2.id


# ── session_event_ids ──────────────────────────────────────────────────────


async def test_session_event_ids_empty(session: Any) -> None:
    assert await events_repo.session_event_ids(session, 1) == []


async def test_session_event_ids_returns_all_in_order(session: Any) -> None:
    ev1 = await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)
    await events_repo.append(session, guild_id=1, type=EventType.SESSION_END)
    ev3 = await events_repo.append(session, guild_id=1, type=EventType.SESSION_START)
    ids = await events_repo.session_event_ids(session, 1)
    assert ids == [ev1.id, ev3.id]


# ── count_sp_base_per_user ─────────────────────────────────────────────────


async def test_count_sp_base_per_user_for_session(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=5)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=5)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=10, session_id=5)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=10, session_id=6)
    counts = await events_repo.count_sp_base_per_user_for_session(session, 1, session_id=5)
    assert counts == {100: 2, 200: 1}


async def test_count_sp_base_per_user_for_chain(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, chain_id=7)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, chain_id=7)
    await _event(session, guild_id=1, user_id=300, type=EventType.SP_BASE, delta=10, chain_id=7)
    counts = await events_repo.count_sp_base_per_user_for_chain(session, 1, chain_id=7)
    assert counts == {100: 2, 300: 1}


async def test_count_sp_base_per_user_only_counts_sp_base(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=5)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_REACTION, delta=1, session_id=5)
    counts = await events_repo.count_sp_base_per_user_for_session(session, 1, session_id=5)
    assert counts[100] == 1  # only SP_BASE, not SP_REACTION


# ── events_in_session / events_for_chain ────────────────────────────────────


async def test_events_in_session_filters_correctly(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, session_id=5)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=10, session_id=6)
    evs = await events_repo.events_in_session(session, 1, session_id=5)
    assert len(evs) == 1
    assert evs[0].user_id == 100


async def test_events_for_chain_filters_correctly(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, chain_id=1)
    await _event(session, guild_id=1, user_id=200, type=EventType.SP_BASE, delta=10, chain_id=2)
    evs = await events_repo.events_for_chain(session, 1, chain_id=1)
    assert len(evs) == 1


# ── top_pp_user ────────────────────────────────────────────────────────────


async def test_top_pp_user_returns_highest_pp(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.PP_BREAK, delta=25)
    await _event(session, guild_id=1, user_id=200, type=EventType.PP_BREAK, delta=40)
    result = await events_repo.top_pp_user(session, 1)
    assert result == (200, 40)


async def test_top_pp_user_returns_none_when_no_pp(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10)
    assert await events_repo.top_pp_user(session, 1) is None


# ── chains_started / chains_broken ─────────────────────────────────────────


async def test_chains_started_and_broken(session: Any) -> None:
    await _event(session, guild_id=1, user_id=100, type=EventType.CHAIN_START)
    await _event(session, guild_id=1, user_id=100, type=EventType.CHAIN_START)
    await _event(session, guild_id=1, user_id=100, type=EventType.CHAIN_BREAK)
    assert await events_repo.chains_started(session, 1, 100) == 2
    assert await events_repo.chains_broken(session, 1, 100) == 1


# ── last_stank_at ──────────────────────────────────────────────────────────


async def test_last_stank_at(session: Any) -> None:
    t1 = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 4, 19, 13, 0, tzinfo=UTC)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, created_at=t1)
    await _event(session, guild_id=1, user_id=100, type=EventType.SP_BASE, delta=10, created_at=t2)
    result = await events_repo.last_stank_at(session, 1, 100)
    assert result is not None
    assert result.hour == 13


async def test_last_stank_at_none_when_no_stank(session: Any) -> None:
    assert await events_repo.last_stank_at(session, 1, 999) is None
