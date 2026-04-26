"""Chain repository — chains + chain_messages.

A chain is alive when ``broken_at IS NULL``. At most one alive chain exists
per altar at a time. ``ChainService`` enforces that invariant; this module
just provides the query primitives.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Chain, ChainMessage


async def current_chain(
    session: AsyncSession, guild_id: int, altar_id: int
) -> Chain | None:
    stmt = (
        select(Chain)
        .where(
            Chain.guild_id == guild_id,
            Chain.altar_id == altar_id,
            Chain.broken_at.is_(None),
        )
        .order_by(Chain.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def start_chain(
    session: AsyncSession,
    *,
    guild_id: int,
    altar_id: int,
    starter_user_id: int,
    session_id: int | None,
    started_at: datetime | None = None,
) -> Chain:
    chain = Chain(
        guild_id=guild_id,
        altar_id=altar_id,
        starter_user_id=starter_user_id,
        session_id=session_id,
        started_at=started_at or datetime.now(tz=UTC),
    )
    session.add(chain)
    await session.flush()
    return chain


async def break_chain(
    session: AsyncSession,
    chain: Chain,
    *,
    broken_by_user_id: int | None,
    broken_at: datetime | None = None,
) -> Chain:
    chain.broken_at = broken_at or datetime.now(tz=UTC)
    chain.broken_by_user_id = broken_by_user_id
    length, unique = await chain_length_and_unique(session, chain.id)
    chain.final_length = length
    chain.final_unique = unique
    return chain


async def append_message(
    session: AsyncSession,
    *,
    chain_id: int,
    message_id: int,
    user_id: int,
    position: int,
    created_at: datetime | None = None,
) -> ChainMessage:
    cm = ChainMessage(
        chain_id=chain_id,
        message_id=message_id,
        user_id=user_id,
        position=position,
        created_at=created_at or datetime.now(tz=UTC),
    )
    session.add(cm)
    await session.flush()
    return cm


async def chain_length_and_unique(
    session: AsyncSession, chain_id: int
) -> tuple[int, int]:
    stmt = select(
        func.count(ChainMessage.message_id),
        func.count(func.distinct(ChainMessage.user_id)),
    ).where(ChainMessage.chain_id == chain_id)
    length, unique = (await session.execute(stmt)).one()
    return int(length or 0), int(unique or 0)


async def messages_in_chain(
    session: AsyncSession, chain_id: int
) -> Sequence[ChainMessage]:
    stmt = (
        select(ChainMessage)
        .where(ChainMessage.chain_id == chain_id)
        .order_by(ChainMessage.position.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def message_in_active_chain(
    session: AsyncSession, guild_id: int, altar_id: int, message_id: int
) -> bool:
    """Return True only if message_id belongs to the current unbroken chain."""
    stmt = (
        select(ChainMessage.message_id)
        .join(Chain, Chain.id == ChainMessage.chain_id)
        .where(
            Chain.guild_id == guild_id,
            Chain.altar_id == altar_id,
            Chain.broken_at.is_(None),
            ChainMessage.message_id == message_id,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def contributors(session: AsyncSession, chain_id: int) -> list[int]:
    """Return the ordered list of ``user_id``s that posted in this chain."""
    stmt = (
        select(ChainMessage.user_id)
        .where(ChainMessage.chain_id == chain_id)
        .order_by(ChainMessage.position.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
