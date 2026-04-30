"""Records repository — session and all-time best-chain cache."""

from __future__ import annotations

from datetime import UTC, datetime

from stankbot.db.models import RecordScope
from stankbot.db.repositories import records as records_repo

# ---------------------------------------------------------------------------
# beats
# ---------------------------------------------------------------------------


def test_beats_longer_chain_wins() -> None:
    assert records_repo.beats(10, 5, 5, 3) is True


def test_beats_shorter_chain_loses() -> None:
    assert records_repo.beats(5, 10, 10, 3) is False


def test_beats_equal_length_more_unique_wins() -> None:
    assert records_repo.beats(5, 10, 5, 3) is True


def test_beats_equal_length_equal_unique_loses() -> None:
    assert records_repo.beats(5, 10, 5, 10) is False


def test_beats_equal_length_fewer_unique_loses() -> None:
    assert records_repo.beats(5, 3, 5, 10) is False


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_returns_none_when_no_record(session) -> None:  # type: ignore[no-untyped-def]
    result = await records_repo.get(
        session, guild_id=1, altar_id=10, scope=RecordScope.SESSION
    )
    assert result is None


async def test_get_returns_record_after_upsert(session) -> None:  # type: ignore[no-untyped-def]
    await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.SESSION,
        chain_length=5,
        unique_count=3,
        chain_id=42,
        session_id=100,
    )
    row = await records_repo.get(session, guild_id=1, altar_id=10, scope=RecordScope.SESSION)
    assert row is not None
    assert row.guild_id == 1
    assert row.altar_id == 10
    assert row.scope == "session"
    assert row.chain_length == 5
    assert row.unique_count == 3
    assert row.chain_id == 42
    assert row.session_id == 100


async def test_get_is_scoped(session) -> None:  # type: ignore[no-untyped-def]
    """get() for SESSION should not return an ALLTIME row."""
    await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.ALLTIME,
        chain_length=8,
        unique_count=4,
        chain_id=99,
        session_id=200,
    )
    sess_row = await records_repo.get(session, guild_id=1, altar_id=10, scope=RecordScope.SESSION)
    assert sess_row is None  # only ALLTIME was upserted


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


async def test_upsert_creates_new_row(session) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
    row = await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.SESSION,
        chain_length=3,
        unique_count=2,
        chain_id=7,
        session_id=101,
        set_at=now,
    )
    assert row.guild_id == 1
    assert row.altar_id == 10
    assert row.scope == "session"
    assert row.chain_length == 3
    assert row.unique_count == 2
    assert row.chain_id == 7
    assert row.session_id == 101
    assert row.set_at == now


async def test_upsert_overwrites_existing_row(session) -> None:  # type: ignore[no-untyped-def]
    """Calling upsert on an existing (guild,altar,scope) overwrites values."""
    await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.SESSION,
        chain_length=5,
        unique_count=2,
        chain_id=1,
        session_id=100,
    )
    await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.SESSION,
        chain_length=12,
        unique_count=8,
        chain_id=2,
        session_id=200,
    )
    row = await records_repo.get(session, guild_id=1, altar_id=10, scope=RecordScope.SESSION)
    assert row is not None
    assert row.chain_length == 12
    assert row.unique_count == 8
    assert row.chain_id == 2
    assert row.session_id == 200


async def test_upsert_scopes_are_independent(session) -> None:  # type: ignore[no-untyped-def]
    """Upserting a SESSION row does not touch the ALLTIME row."""
    await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.ALLTIME,
        chain_length=12,
        unique_count=6,
        chain_id=5,
        session_id=300,
    )
    await records_repo.upsert(
        session,
        guild_id=1,
        altar_id=10,
        scope=RecordScope.SESSION,
        chain_length=3,
        unique_count=2,
        chain_id=9,
        session_id=400,
    )
    alltime = await records_repo.get(session, guild_id=1, altar_id=10, scope=RecordScope.ALLTIME)
    assert alltime is not None
    assert alltime.chain_length == 12
    assert alltime.unique_count == 6
    assert alltime.chain_id == 5
    assert alltime.session_id == 300

    session_row = await records_repo.get(session, guild_id=1, altar_id=10, scope=RecordScope.SESSION)
    assert session_row is not None
    assert session_row.chain_length == 3
    assert session_row.unique_count == 2
    assert session_row.chain_id == 9
    assert session_row.session_id == 400
