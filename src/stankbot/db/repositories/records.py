"""Records cache — session + all-time best chains per altar.

The ``records`` table is a read-through cache. ``rebuild-from-history``
drops + recomputes it from the event + chain log; nothing is ever lost
by clearing it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Record, RecordScope


async def get(
    session: AsyncSession,
    *,
    guild_id: int,
    altar_id: int,
    scope: RecordScope,
) -> Record | None:
    return await session.get(Record, (guild_id, altar_id, str(scope)))


async def upsert(
    session: AsyncSession,
    *,
    guild_id: int,
    altar_id: int,
    scope: RecordScope,
    chain_length: int,
    unique_count: int,
    chain_id: int | None,
    session_id: int | None,
    set_at: datetime | None = None,
) -> Record:
    record = await session.get(Record, (guild_id, altar_id, str(scope)))
    now = set_at or datetime.now(tz=UTC)
    if record is None:
        record = Record(
            guild_id=guild_id,
            altar_id=altar_id,
            scope=str(scope),
            chain_length=chain_length,
            unique_count=unique_count,
            chain_id=chain_id,
            session_id=session_id,
            set_at=now,
        )
        session.add(record)
    else:
        record.chain_length = chain_length
        record.unique_count = unique_count
        record.chain_id = chain_id
        record.session_id = session_id
        record.set_at = now
    return record


def beats(
    new_length: int,
    new_unique: int,
    current_length: int,
    current_unique: int,
) -> bool:
    """Tie-breaker: longer chain wins; equal length → more unique
    contributors wins.
    """
    if new_length > current_length:
        return True
    return new_length == current_length and new_unique > current_unique
