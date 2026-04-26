"""Chains repository — unit tests against in-memory SQLite.

Locks in behaviour for:
    * start_chain
    * current_chain (alive filter, ordering)
    * break_chain (final_length, final_unique)
    * append_message (position tracking)
    * chain_length_and_unique
    * contributors / messages_in_chain
    * message_in_active_chain
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from stankbot.db.repositories import chains as chains_repo

# ── helpers ────────────────────────────────────────────────────────────────


async def _start_chain(
    session: Any, guild_id: int = 1, altar_id: int = 1, starter_id: int = 100,
    session_id: int = 1,
) -> Any:
    return await chains_repo.start_chain(
        session,
        guild_id=guild_id,
        altar_id=altar_id,
        starter_user_id=starter_id,
        session_id=session_id,
    )


async def _append_message(
    session: Any, chain_id: int, message_id: int, user_id: int, position: int,
) -> Any:
    return await chains_repo.append_message(
        session,
        chain_id=chain_id,
        message_id=message_id,
        user_id=user_id,
        position=position,
    )


# ── start_chain ─────────────────────────────────────────────────────────────


async def test_start_chain_persists(session: Any) -> None:
    chain = await _start_chain(session)
    assert chain.id is not None
    assert chain.guild_id == 1
    assert chain.altar_id == 1
    assert chain.starter_user_id == 100
    assert chain.session_id == 1
    assert chain.broken_at is None
    assert chain.broken_by_user_id is None


# ── current_chain ───────────────────────────────────────────────────────────


async def test_current_chain_none_when_no_chain(session: Any) -> None:
    assert await chains_repo.current_chain(session, 1, 1) is None


async def test_current_chain_returns_only_alive(session: Any) -> None:
    chain = await _start_chain(session, starter_id=200)
    found = await chains_repo.current_chain(session, 1, 1)
    assert found is not None
    assert found.id == chain.id


async def test_current_chain_ignores_broken(session: Any) -> None:
    chain = await _start_chain(session, starter_id=200)
    await chains_repo.break_chain(session, chain, broken_by_user_id=300)
    assert await chains_repo.current_chain(session, 1, 1) is None


async def test_current_chain_returns_most_recent_alive(session: Any) -> None:
    c1 = await _start_chain(session, starter_id=200)
    await chains_repo.break_chain(session, c1, broken_by_user_id=300)
    c2 = await _start_chain(session, starter_id=400)
    found = await chains_repo.current_chain(session, 1, 1)
    assert found is not None
    assert found.id == c2.id


# ── break_chain ─────────────────────────────────────────────────────────────


async def test_break_chain_sets_broken_fields(session: Any) -> None:
    chain = await _start_chain(session, starter_id=200)
    t = datetime(2026, 4, 19, 15, 0, tzinfo=UTC)
    result = await chains_repo.break_chain(session, chain, broken_by_user_id=300, broken_at=t)
    assert result.broken_by_user_id == 300
    assert result.broken_at == t


async def test_break_chain_stores_final_length(session: Any) -> None:
    chain = await _start_chain(session, starter_id=200)
    await _append_message(session, chain.id, message_id=1001, user_id=200, position=1)
    await _append_message(session, chain.id, message_id=1002, user_id=300, position=2)
    await _append_message(session, chain.id, message_id=1003, user_id=200, position=3)
    await chains_repo.break_chain(session, chain, broken_by_user_id=400)
    # Re-fetch to see the updated values
    from sqlalchemy import select

    from stankbot.db.models import Chain
    updated = (await session.execute(select(Chain).where(Chain.id == chain.id))).scalar_one()
    assert updated.final_length == 3
    assert updated.final_unique == 2  # user 200 and 300


async def test_break_chain_empty_chain_zero_length(session: Any) -> None:
    chain = await _start_chain(session, starter_id=200)
    await chains_repo.break_chain(session, chain, broken_by_user_id=300)
    from sqlalchemy import select

    from stankbot.db.models import Chain
    updated = (await session.execute(select(Chain).where(Chain.id == chain.id))).scalar_one()
    assert updated.final_length == 0
    assert updated.final_unique == 0


# ── append_message ──────────────────────────────────────────────────────────


async def test_append_message_persists(session: Any) -> None:
    chain = await _start_chain(session)
    cm = await _append_message(session, chain.id, message_id=1001, user_id=200, position=1)
    assert cm.message_id == 1001
    assert cm.user_id == 200
    assert cm.position == 1
    assert cm.chain_id == chain.id


# ── chain_length_and_unique ─────────────────────────────────────────────────


async def test_chain_length_and_unique_zero_zero_for_empty(session: Any) -> None:
    chain = await _start_chain(session)
    length, unique = await chains_repo.chain_length_and_unique(session, chain.id)
    assert length == 0
    assert unique == 0


async def test_chain_length_and_unique_counts_correctly(session: Any) -> None:
    chain = await _start_chain(session)
    await _append_message(session, chain.id, 1, 100, 1)  # user 100
    await _append_message(session, chain.id, 2, 100, 2)  # user 100 again
    await _append_message(session, chain.id, 3, 200, 3)  # user 200
    length, unique = await chains_repo.chain_length_and_unique(session, chain.id)
    assert length == 3
    assert unique == 2


async def test_chain_length_and_unique_all_unique(session: Any) -> None:
    chain = await _start_chain(session)
    for i, uid in enumerate([100, 200, 300, 400, 500], start=1):
        await _append_message(session, chain.id, message_id=i, user_id=uid, position=i)
    length, unique = await chains_repo.chain_length_and_unique(session, chain.id)
    assert length == 5
    assert unique == 5


async def test_chain_length_and_unique_single_user(session: Any) -> None:
    chain = await _start_chain(session)
    for i in range(1, 4):
        await _append_message(session, chain.id, message_id=i, user_id=100, position=i)
    length, unique = await chains_repo.chain_length_and_unique(session, chain.id)
    assert length == 3
    assert unique == 1


# ── contributors ────────────────────────────────────────────────────────────


async def test_contributors_ordered_by_position(session: Any) -> None:
    chain = await _start_chain(session)
    await _append_message(session, chain.id, 1, 300, 1)
    await _append_message(session, chain.id, 2, 100, 2)
    await _append_message(session, chain.id, 3, 200, 3)
    users = await chains_repo.contributors(session, chain.id)
    assert users == [300, 100, 200]


async def test_contributors_empty_chain(session: Any) -> None:
    chain = await _start_chain(session)
    assert await chains_repo.contributors(session, chain.id) == []


# ── messages_in_chain ───────────────────────────────────────────────────────


async def test_messages_in_chain_ordered_by_position(session: Any) -> None:
    chain = await _start_chain(session)
    await _append_message(session, chain.id, 10, 100, 2)
    await _append_message(session, chain.id, 5, 200, 1)
    msgs = await chains_repo.messages_in_chain(session, chain.id)
    assert [m.message_id for m in msgs] == [5, 10]


# ── message_in_active_chain ─────────────────────────────────────────────────


async def test_message_in_active_chain_true_for_alive(session: Any) -> None:
    chain = await _start_chain(session)
    await _append_message(session, chain.id, 42, 100, 1)
    assert await chains_repo.message_in_active_chain(session, 1, 1, 42) is True


async def test_message_in_active_chain_false_for_broken(session: Any) -> None:
    chain = await _start_chain(session)
    await _append_message(session, chain.id, 42, 100, 1)
    await chains_repo.break_chain(session, chain, broken_by_user_id=200)
    assert await chains_repo.message_in_active_chain(session, 1, 1, 42) is False


async def test_message_in_active_chain_false_for_unknown_message(session: Any) -> None:
    chain = await _start_chain(session)
    await _append_message(session, chain.id, 42, 100, 1)
    assert await chains_repo.message_in_active_chain(session, 1, 1, 99) is False
