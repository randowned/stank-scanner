"""player_chain_totals repository — unit tests against in-memory SQLite.

Covers:
    * upsert (new row, cumulative delta, idempotent)
    * get (single row)
    * get_for_user (all chains for a user)
    * get_for_chain (all users for a chain)
    * rebuild (from events)
    * delete_for_chain
"""

from __future__ import annotations

from typing import Any

from stankbot.db.models import Chain, EventType, Guild, PlayerChainTotal
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import player_chain_totals as pct_repo


# ── helpers ────────────────────────────────────────────────────────────────


async def _event(
    session: Any,
    *,
    guild_id: int = 1,
    user_id: int,
    type: EventType | str,
    chain_id: int | None = None,
    session_id: int | None = None,
) -> None:
    await events_repo.append(
        session,
        guild_id=guild_id,
        type=type,
        delta=10 if type == EventType.SP_BASE else 1,
        user_id=user_id,
        chain_id=chain_id,
        session_id=session_id,
    )


async def _ensure_guild(session: Any, guild_id: int = 1) -> None:
    session.add(Guild(id=guild_id, name="Test"))
    await session.flush()


# ── upsert ─────────────────────────────────────────────────────────────────


async def test_upsert_creates_row(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    row = await pct_repo.get(session, 1, 100, 5)
    assert row is not None
    assert row.stanks_in_chain == 1
    assert row.reactions_in_chain == 0


async def test_upsert_accumulates_counters(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=2, reactions_delta=1)
    row = await pct_repo.get(session, 1, 100, 5)
    assert row.stanks_in_chain == 3
    assert row.reactions_in_chain == 1


async def test_upsert_separate_chains(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=6, stanks_delta=2)
    row5 = await pct_repo.get(session, 1, 100, 5)
    row6 = await pct_repo.get(session, 1, 100, 6)
    assert row5.stanks_in_chain == 1
    assert row6.stanks_in_chain == 2


async def test_upsert_separate_users(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    await pct_repo.upsert(session, guild_id=1, user_id=200, chain_id=5, stanks_delta=2)
    row_a = await pct_repo.get(session, 1, 100, 5)
    row_b = await pct_repo.get(session, 1, 200, 5)
    assert row_a.stanks_in_chain == 1
    assert row_b.stanks_in_chain == 2


# ── get ────────────────────────────────────────────────────────────────────


async def test_get_returns_none_when_missing(session: Any) -> None:
    assert await pct_repo.get(session, 1, 999, 5) is None


async def test_get_returns_row_when_present(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=3)
    row = await pct_repo.get(session, 1, 100, 5)
    assert row is not None
    assert row.stanks_in_chain == 3


# ── get_for_user ────────────────────────────────────────────────────────────────


async def test_get_for_user_returns_all_chains(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=6, stanks_delta=2)
    await pct_repo.upsert(session, guild_id=1, user_id=200, chain_id=5, stanks_delta=3)

    result = await pct_repo.get_for_user(session, 1, 100)
    assert len(result) == 2
    assert result[5].stanks_in_chain == 1
    assert result[6].stanks_in_chain == 2


async def test_get_for_user_returns_empty_for_none(session: Any) -> None:
    result = await pct_repo.get_for_user(session, 1, 999)
    assert result == {}


# ── get_for_chain ────────────────────────────────────────────────────────


async def test_get_for_chain_returns_all_users(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    await pct_repo.upsert(session, guild_id=1, user_id=200, chain_id=5, stanks_delta=2)
    await pct_repo.upsert(session, guild_id=1, user_id=300, chain_id=6, stanks_delta=3)

    result = await pct_repo.get_for_chain(session, 1, 5)
    assert len(result) == 2
    assert result[100].stanks_in_chain == 1
    assert result[200].stanks_in_chain == 2


async def test_get_for_chain_returns_empty_for_none(session: Any) -> None:
    result = await pct_repo.get_for_chain(session, 1, 999)
    assert result == {}


# ── rebuild ────────────────────────────────────────────────────────────────


async def test_rebuild_empty_guild_returns_zero(session: Any) -> None:
    await _ensure_guild(session)
    count = await pct_repo.rebuild(session, 1)
    assert count == 0


async def test_rebuild_populates_from_events(session: Any) -> None:
    await _ensure_guild(session)

    chain_id = (await events_repo.append(session, guild_id=1, type=EventType.CHAIN_START)).id

    await _event(session, user_id=100, type=EventType.SP_BASE, chain_id=chain_id)
    await _event(session, user_id=100, type=EventType.SP_BASE, chain_id=chain_id)
    await _event(session, user_id=200, type=EventType.SP_BASE, chain_id=chain_id)
    await _event(session, user_id=100, type=EventType.SP_REACTION, chain_id=chain_id)
    await session.flush()

    count = await pct_repo.rebuild(session, 1)
    assert count == 2  # 2 users (100, 200)

    row_100 = await pct_repo.get(session, 1, 100, chain_id)
    row_200 = await pct_repo.get(session, 1, 200, chain_id)
    assert row_100.stanks_in_chain == 2
    assert row_100.reactions_in_chain == 1
    assert row_200.stanks_in_chain == 1
    assert row_200.reactions_in_chain == 0


async def test_rebuild_replaces_existing_rows(session: Any) -> None:
    """Rebuilding twice should not double-count."""
    await _ensure_guild(session)
    chain_id = (await events_repo.append(session, guild_id=1, type=EventType.CHAIN_START)).id

    await _event(session, user_id=100, type=EventType.SP_BASE, chain_id=chain_id)
    await session.flush()

    await pct_repo.rebuild(session, 1)
    await pct_repo.rebuild(session, 1)

    row = await pct_repo.get(session, 1, 100, chain_id)
    assert row.stanks_in_chain == 1


async def test_rebuild_idempotent(session: Any) -> None:
    await _ensure_guild(session)
    chain_id = (await events_repo.append(session, guild_id=1, type=EventType.CHAIN_START)).id

    await _event(session, user_id=100, type=EventType.SP_BASE, chain_id=chain_id)
    await _event(session, user_id=200, type=EventType.SP_BASE, chain_id=chain_id)
    await session.flush()

    count1 = await pct_repo.rebuild(session, 1)
    count2 = await pct_repo.rebuild(session, 1)

    assert count1 == count2


# ── delete_for_chain ─────────────────────────────────────────────────────


async def test_delete_for_chain_removes_rows(session: Any) -> None:
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=5, stanks_delta=1)
    await pct_repo.upsert(session, guild_id=1, user_id=200, chain_id=5, stanks_delta=2)
    await pct_repo.upsert(session, guild_id=1, user_id=100, chain_id=6, stanks_delta=3)

    await pct_repo.delete_for_chain(session, 1, 5)

    assert await pct_repo.get(session, 1, 100, 5) is None
    assert await pct_repo.get(session, 1, 200, 5) is None
    assert (await pct_repo.get(session, 1, 100, 6)).stanks_in_chain == 3