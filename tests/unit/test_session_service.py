"""SessionService: event-sourced lifecycle and replay."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from stankbot.db.models import (
    Altar,
    EventType,
    Guild,
    Record,
    RecordScope,
    SessionEndReason,
)
from stankbot.db.repositories import events as events_repo
from stankbot.db.repositories import records as records_repo
from stankbot.services.session_service import SessionService


@pytest.fixture
async def guild(session):  # type: ignore[no-untyped-def]
    g = Guild(id=1, name="Maphra")
    session.add(g)
    await session.flush()
    return g


@pytest.fixture
async def guild_with_altar(session):  # type: ignore[no-untyped-def]
    """Guild + primary altar for record-scoped tests."""
    g = Guild(id=1, name="Maphra")
    session.add(g)
    await session.flush()
    altar = Altar(
        guild_id=1,
        channel_id=200,
        sticker_id=300,
        display_name="primary",
    )
    session.add(altar)
    await session.flush()
    return g, altar


async def _count_session_records(session, guild_id: int) -> int:
    """Return how many SESSION scope records exist for a guild."""
    result = await session.execute(
        select(Record).where(
            Record.guild_id == guild_id,
            Record.scope == str(RecordScope.SESSION),
        )
    )
    return len(result.scalars().all())


async def test_current_is_none_before_ensure_started(session, guild) -> None:  # type: ignore[no-untyped-def]
    svc = SessionService(session=session)
    assert await svc.current(guild.id) is None


async def test_ensure_started_emits_session_start_once(session, guild) -> None:  # type: ignore[no-untyped-def]
    svc = SessionService(session=session)
    first = await svc.ensure_started(guild.id)
    second = await svc.ensure_started(guild.id)
    assert first == second  # idempotent while the session is alive
    # Exactly one session_start event
    ids = await events_repo.session_event_ids(session, guild.id)
    assert ids == [first]


async def test_end_session_emits_end_then_start(session, guild) -> None:  # type: ignore[no-untyped-def]
    svc = SessionService(session=session)
    s1 = await svc.ensure_started(guild.id, when=datetime(2026, 4, 19, 0, 0, tzinfo=UTC))
    ended, s2 = await svc.end_session(
        guild.id,
        reason=SessionEndReason.AUTO,
        when=datetime(2026, 4, 19, 7, 0, tzinfo=UTC),
    )
    assert ended == s1
    assert s2 is not None and s2 != s1
    # Sessions in order
    assert await events_repo.session_event_ids(session, guild.id) == [s1, s2]


async def test_end_session_with_open_new_false(session, guild) -> None:  # type: ignore[no-untyped-def]
    svc = SessionService(session=session)
    s1 = await svc.ensure_started(guild.id)
    ended, new = await svc.end_session(
        guild.id, reason=SessionEndReason.BOARD_RESET, open_new=False
    )
    assert ended == s1
    assert new is None
    # No alive session after a reset without re-open.
    assert await svc.current(guild.id) is None
    s2 = await svc.ensure_started(guild.id)
    assert s2 != s1


async def test_session_events_slice(session, guild) -> None:  # type: ignore[no-untyped-def]
    svc = SessionService(session=session)
    s1 = await svc.ensure_started(guild.id)
    # Inject a scoring event in session 1
    await events_repo.append(
        session,
        guild_id=guild.id,
        type=EventType.SP_BASE,
        delta=10,
        user_id=42,
        session_id=s1,
    )
    await svc.end_session(guild.id, reason=SessionEndReason.AUTO)
    s2 = await svc.current(guild.id)
    await events_repo.append(
        session,
        guild_id=guild.id,
        type=EventType.SP_BASE,
        delta=20,
        user_id=42,
        session_id=s2,
    )

    s1_events = await svc.session_events(guild.id, s1)
    s2_events = await svc.session_events(guild.id, s2)
    assert [e.delta for e in s1_events if e.type == EventType.SP_BASE] == [10]
    assert [e.delta for e in s2_events if e.type == EventType.SP_BASE] == [20]


# ---------------------------------------------------------------------------
# Record reset on session boundaries
# ---------------------------------------------------------------------------


async def test_end_session_resets_session_records(session, guild_with_altar) -> None:  # type: ignore[no-untyped-def]
    guild, altar = guild_with_altar
    svc = SessionService(session=session)

    # Populate both SESSION and ALLTIME records
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.SESSION,
        chain_length=5,
        unique_count=3,
        chain_id=1,
        session_id=100,
    )
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.ALLTIME,
        chain_length=5,
        unique_count=3,
        chain_id=1,
        session_id=100,
    )
    await session.commit()

    await svc.ensure_started(guild.id)
    await svc.end_session(guild.id, reason=SessionEndReason.AUTO, open_new=True)

    # SESSION records should be deleted
    assert await _count_session_records(session, guild.id) == 0
    # ALLTIME record should survive
    alltime = await records_repo.get(
        session, guild_id=guild.id, altar_id=altar.id, scope=RecordScope.ALLTIME
    )
    assert alltime is not None
    assert alltime.chain_length == 5


async def test_ensure_started_resets_session_records_when_dead(session, guild_with_altar) -> None:  # type: ignore[no-untyped-def]
    guild, altar = guild_with_altar
    svc = SessionService(session=session)

    # Seed a SESSION record (simulating a previous session that left one behind)
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.SESSION,
        chain_length=8,
        unique_count=4,
        chain_id=2,
        session_id=200,
    )
    # Seed ALLTIME record too
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.ALLTIME,
        chain_length=8,
        unique_count=4,
        chain_id=2,
        session_id=200,
    )
    await session.commit()

    # No session alive — ensure_started should create one AND reset records
    await svc.ensure_started(guild.id)

    assert await _count_session_records(session, guild.id) == 0
    alltime = await records_repo.get(
        session, guild_id=guild.id, altar_id=altar.id, scope=RecordScope.ALLTIME
    )
    assert alltime is not None
    assert alltime.chain_length == 8


async def test_ensure_started_does_not_reset_records_when_session_alive(
    session, guild_with_altar
) -> None:  # type: ignore[no-untyped-def]
    guild, altar = guild_with_altar
    svc = SessionService(session=session)

    await svc.ensure_started(guild.id)

    # Seed a SESSION record via the chain service path (simulates mid-session record)
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.SESSION,
        chain_length=3,
        unique_count=2,
        chain_id=5,
        session_id=1,
    )
    await session.commit()

    # Session is alive — ensure_started should be idempotent and NOT reset records
    await svc.ensure_started(guild.id)

    assert await _count_session_records(session, guild.id) == 1
    sess_row = await records_repo.get(
        session, guild_id=guild.id, altar_id=altar.id, scope=RecordScope.SESSION
    )
    assert sess_row is not None
    assert sess_row.chain_length == 3


async def test_end_session_without_open_new_resets_session_records(
    session, guild_with_altar
) -> None:  # type: ignore[no-untyped-def]
    guild, altar = guild_with_altar
    svc = SessionService(session=session)

    await svc.ensure_started(guild.id)
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.SESSION,
        chain_length=12,
        unique_count=6,
        chain_id=9,
        session_id=1,
    )
    await session.commit()

    await svc.end_session(guild.id, reason=SessionEndReason.BOARD_RESET, open_new=False)

    assert await _count_session_records(session, guild.id) == 0


async def test_end_session_preserves_alltime_record_on_close(
    session, guild_with_altar
) -> None:  # type: ignore[no-untyped-def]
    guild, altar = guild_with_altar
    svc = SessionService(session=session)

    await svc.ensure_started(guild.id)
    await records_repo.upsert(
        session,
        guild_id=guild.id,
        altar_id=altar.id,
        scope=RecordScope.ALLTIME,
        chain_length=15,
        unique_count=7,
        chain_id=10,
        session_id=1,
    )
    await session.commit()

    await svc.end_session(guild.id, reason=SessionEndReason.AUTO, open_new=True)

    alltime = await records_repo.get(
        session, guild_id=guild.id, altar_id=altar.id, scope=RecordScope.ALLTIME
    )
    assert alltime is not None
    assert alltime.chain_length == 15


async def test_end_session_noop_when_no_session_does_not_crash(
    session, guild
) -> None:  # type: ignore[no-untyped-def]
    """Calling end_session on a guild with no alive session is a no-op."""
    svc = SessionService(session=session)
    ended, new = await svc.end_session(
        guild.id, reason=SessionEndReason.AUTO, open_new=True
    )
    assert ended is None  # nothing to end
    assert new is not None  # still starts a new session
    # No crash — the _reset_session_records is skipped because neither
    # ended_id nor new_id was set... wait, new_id IS set. But the
    # query is a DELETE, so when there are no rows it's just a no-op.
    assert await _count_session_records(session, guild.id) == 0
