"""Repository tests for media milestones — insert, dedup, existence check."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import Guild, MediaItem
from stankbot.db.repositories import media as media_repo


# ── helpers ─────────────────────────────────────────────────────────────────


async def _guild(session: AsyncSession, guild_id: int = 1) -> None:
    session.add(Guild(id=guild_id))


async def _media_item(
    session: AsyncSession,
    guild_id: int = 1,
    item_id: int | None = None,
    media_type: str = "youtube",
    external_id: str = "vid_001",
    title: str = "Test Video",
) -> MediaItem:
    item = MediaItem(
        guild_id=guild_id,
        media_type=media_type,
        external_id=external_id,
        title=title,
        added_by=100,
    )
    if item_id is not None:
        item.id = item_id
    session.add(item)
    await session.flush()
    return item


# ── insert_milestone ────────────────────────────────────────────────────────


async def test_insert_milestone_persists(session: Any) -> None:
    await _guild(session)
    item = await _media_item(session)

    result = await media_repo.insert_milestone(
        session, item.id, "view_count", 1_000_000,
    )
    assert result is not None
    assert result.media_item_id == item.id
    assert result.metric_key == "view_count"
    assert result.milestone_value == 1_000_000
    assert result.announced_at is not None


async def test_insert_milestone_deduplicates(session: Any) -> None:
    """Second insert of same (item, metric, value) should return None."""
    await _guild(session)
    item = await _media_item(session)

    first = await media_repo.insert_milestone(
        session, item.id, "view_count", 1_000_000,
    )
    assert first is not None

    second = await media_repo.insert_milestone(
        session, item.id, "view_count", 1_000_000,
    )
    assert second is None


async def test_insert_milestone_different_values_ok(session: Any) -> None:
    await _guild(session)
    item = await _media_item(session)

    first = await media_repo.insert_milestone(
        session, item.id, "view_count", 1_000_000,
    )
    assert first is not None

    second = await media_repo.insert_milestone(
        session, item.id, "view_count", 2_000_000,
    )
    assert second is not None
    assert second.milestone_value == 2_000_000


async def test_insert_milestone_different_items_ok(session: Any) -> None:
    await _guild(session)
    item1 = await _media_item(session, external_id="vid_001")
    item2 = await _media_item(session, external_id="vid_002")

    first = await media_repo.insert_milestone(
        session, item1.id, "view_count", 1_000_000,
    )
    assert first is not None

    second = await media_repo.insert_milestone(
        session, item2.id, "view_count", 1_000_000,
    )
    assert second is not None


async def test_insert_milestone_different_metrics_ok(session: Any) -> None:
    await _guild(session)
    item = await _media_item(session)

    first = await media_repo.insert_milestone(
        session, item.id, "view_count", 1_000_000,
    )
    assert first is not None

    second = await media_repo.insert_milestone(
        session, item.id, "playcount", 1_000_000,
    )
    assert second is not None


async def test_insert_milestone_many_values_ok(session: Any) -> None:
    """Inserting many milestones for the same item works."""
    await _guild(session)
    item = await _media_item(session)

    for mv in [1_000_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000]:
        result = await media_repo.insert_milestone(
            session, item.id, "view_count", mv,
        )
        assert result is not None
        assert result.milestone_value == mv


# ── has_milestone ───────────────────────────────────────────────────────────


async def test_has_milestone_positive(session: Any) -> None:
    await _guild(session)
    item = await _media_item(session)

    await media_repo.insert_milestone(
        session, item.id, "view_count", 5_000_000,
    )
    assert await media_repo.has_milestone(session, item.id, "view_count", 5_000_000)


async def test_has_milestone_negative(session: Any) -> None:
    await _guild(session)
    item = await _media_item(session)
    assert not await media_repo.has_milestone(session, item.id, "view_count", 999)


async def test_has_milestone_wrong_metric(session: Any) -> None:
    await _guild(session)
    item = await _media_item(session)

    await media_repo.insert_milestone(
        session, item.id, "view_count", 1_000_000,
    )
    assert not await media_repo.has_milestone(session, item.id, "like_count", 1_000_000)


async def test_has_milestone_wrong_item(session: Any) -> None:
    await _guild(session)
    item1 = await _media_item(session, external_id="vid_001")
    item2 = await _media_item(session, external_id="vid_002")

    await media_repo.insert_milestone(
        session, item1.id, "view_count", 1_000_000,
    )
    assert not await media_repo.has_milestone(session, item2.id, "view_count", 1_000_000)
