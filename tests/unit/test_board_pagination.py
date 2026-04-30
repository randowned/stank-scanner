"""Tests for board API pagination."""

from __future__ import annotations

from typing import Any

from stankbot.db.models import Guild, PlayerTotal
from stankbot.db.repositories import player_totals as pt_repo


async def test_player_totals_pagination_with_offset(session: Any) -> None:
    """Test that player_totals query with offset>0 returns correct page."""
    from sqlalchemy import select

    session.add(Guild(id=1, name="Test"))
    await session.flush()

    # Create 25 players with different scores
    for i in range(25):
        await pt_repo.upsert(
            session,
            guild_id=1,
            user_id=1000 + i,
            session_id=1,
            sp_delta=100 + i,  # Scores 100-124
        )
    await session.flush()

    # Fetch second page (offset=20, limit=20)
    stmt = (
        select(PlayerTotal)
        .where(
            PlayerTotal.guild_id == 1,
            PlayerTotal.session_id == 1,
        )
        .order_by((PlayerTotal.earned_sp - PlayerTotal.punishments).desc())
        .offset(20)
        .limit(20)
    )
    rows = (await session.execute(stmt)).scalars().all()

    # Should return 5 players (positions 21-25)
    assert len(rows) == 5
    # Highest score in this batch should be 104 (rank 21)
    assert rows[0].earned_sp == 104


async def test_player_totals_pagination_empty_page(session: Any) -> None:
    """Test that offset beyond available data returns empty list."""
    from sqlalchemy import select

    session.add(Guild(id=1, name="Test"))
    await session.flush()

    # Only 3 players total
    for i in range(3):
        await pt_repo.upsert(
            session,
            guild_id=1,
            user_id=1000 + i,
            session_id=1,
            sp_delta=100 + i,
        )
    await session.flush()

    # Request page beyond available
    stmt = (
        select(PlayerTotal)
        .where(
            PlayerTotal.guild_id == 1,
            PlayerTotal.session_id == 1,
        )
        .offset(100)
        .limit(20)
    )
    rows = (await session.execute(stmt)).scalars().all()

    assert len(rows) == 0
