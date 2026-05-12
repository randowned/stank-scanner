"""Repository tests for media milestones — insert, dedup, existence check, and media owners."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


# ── media owners ──────────────────────────────────────────────────────────


async def test_upsert_owner_creates(session: Any) -> None:
    owner = await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_test",
        name="Test Channel",
        external_url="https://youtube.com/channel/UC_test",
        thumbnail_url="https://example.com/thumb.jpg",
    )
    assert owner.id is not None
    assert owner.media_type == "youtube"
    assert owner.external_id == "UC_test"
    assert owner.name == "Test Channel"
    assert owner.external_url == "https://youtube.com/channel/UC_test"
    assert owner.thumbnail_url == "https://example.com/thumb.jpg"


async def test_upsert_owner_updates(session: Any) -> None:
    owner1 = await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_test2",
        name="Old Name",
        external_url="https://youtube.com/channel/UC_test2",
    )
    owner2 = await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_test2",
        name="New Name",
        external_url="https://youtube.com/channel/UC_test2",
    )
    assert owner1.id == owner2.id
    assert owner2.name == "New Name"


async def test_get_owner_found(session: Any) -> None:
    await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_found",
        name="Found Channel",
        external_url="https://youtube.com/channel/UC_found",
    )
    owner = await media_repo.get_owner(session, "youtube", "UC_found")
    assert owner is not None
    assert owner.name == "Found Channel"


async def test_get_owner_not_found(session: Any) -> None:
    owner = await media_repo.get_owner(session, "youtube", "nonexistent")
    assert owner is None


async def test_insert_owner_snapshot(session: Any) -> None:
    owner = await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_snap",
        name="Snap Channel",
        external_url="https://youtube.com/channel/UC_snap",
    )
    now = datetime.now(UTC)
    snap = await media_repo.insert_owner_snapshot(
        session, owner.id, "subscriber_count", 1000000, now,
    )
    assert snap.id is not None
    assert snap.media_owner_id == owner.id
    assert snap.metric_key == "subscriber_count"
    assert snap.value == 1000000


async def test_get_owner_latest_metrics(session: Any) -> None:
    owner = await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_metrics",
        name="Metrics Channel",
        external_url="https://youtube.com/channel/UC_metrics",
    )
    now = datetime.now(UTC)
    await media_repo.insert_owner_snapshot(session, owner.id, "subscriber_count", 500000, now)
    await media_repo.insert_owner_snapshot(session, owner.id, "view_count", 10000000, now)
    await media_repo.insert_owner_snapshot(session, owner.id, "subscriber_count", 600000, now)

    metrics = await media_repo.get_owner_latest_metrics(session, owner.id)
    assert metrics["subscriber_count"]["value"] == 600000
    assert metrics["view_count"]["value"] == 10000000


async def test_get_owner_snapshots_pivoted(session: Any) -> None:
    owner = await media_repo.upsert_owner(
        session,
        media_type="youtube",
        external_id="UC_pivoted",
        name="Pivoted Channel",
        external_url="https://youtube.com/channel/UC_pivoted",
    )
    now = datetime.now(UTC)
    await media_repo.insert_owner_snapshot(session, owner.id, "subscriber_count", 100, now)
    await media_repo.insert_owner_snapshot(session, owner.id, "view_count", 200, now)

    rows = await media_repo.get_owner_snapshots_pivoted(session, owner.id, limit=5)
    assert len(rows) == 1
    row = rows[0]
    assert row.get("subscriber_count") == 100
    assert row.get("view_count") == 200
    assert "fetched_at" in row
