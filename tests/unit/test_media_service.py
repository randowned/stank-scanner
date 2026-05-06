"""Unit tests for media_service — alignment_mask, aggregation, flooring,
and add_resolved_media metrics_last_fetched_at."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from stankbot.db.models import Guild
from stankbot.services.media_providers.base import ResolvedMedia
from stankbot.services.media_providers.registry import MediaProviderRegistry
from stankbot.services.media_providers.youtube import YouTubeProvider
from stankbot.services.media_service import (
    ALIGN_5MIN,
    ALIGN_15MIN,
    ALIGN_30MIN,
    ALIGN_DAILY,
    ALIGN_HOURLY,
    ALIGN_MONTHLY,
    ALIGN_WEEKLY,
    MediaService,
    _aggregate_snapshots,
    _compute_alignment_mask,
    _floor_to_bucket,
)


@dataclass
class _FakeSnapshot:
    value: int
    fetched_at: datetime


def _make_snaps(start: datetime, values: list[int], interval_mins: int = 15):
    from datetime import timedelta

    return [
        _FakeSnapshot(value=v, fetched_at=start + timedelta(minutes=i * interval_mins))
        for i, v in enumerate(values)
    ]


class TestComputeAlignmentMask:
    def test_sub_minute_accidental(self) -> None:
        """14:00:07 — seconds drift ignored, still aligns to all sub-daily."""
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 14, 0, 7, tzinfo=UTC))
        assert mask & ALIGN_5MIN
        assert mask & ALIGN_15MIN
        assert mask & ALIGN_30MIN
        assert mask & ALIGN_HOURLY

    def test_14_05(self) -> None:
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 14, 5, 0, tzinfo=UTC))
        assert mask & ALIGN_5MIN
        assert not (mask & ALIGN_15MIN)

    def test_14_15(self) -> None:
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 14, 15, 0, tzinfo=UTC))
        assert mask & ALIGN_5MIN
        assert mask & ALIGN_15MIN
        assert not (mask & ALIGN_30MIN)

    def test_14_30(self) -> None:
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 14, 30, 0, tzinfo=UTC))
        assert mask & ALIGN_5MIN
        assert mask & ALIGN_15MIN
        assert mask & ALIGN_30MIN
        assert not (mask & ALIGN_HOURLY)

    def test_midnight_daily(self) -> None:
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC))
        assert mask & ALIGN_HOURLY
        assert mask & ALIGN_DAILY
        assert not (mask & ALIGN_WEEKLY)  # Thursday
        assert mask & ALIGN_MONTHLY      # 1st

    def test_monday_midnight(self) -> None:
        mask = _compute_alignment_mask(datetime(2026, 5, 4, 0, 0, 0, tzinfo=UTC))  # Monday
        assert mask & ALIGN_DAILY
        assert mask & ALIGN_WEEKLY
        assert not (mask & ALIGN_MONTHLY)  # not 1st

    def test_midnight_is_daily(self) -> None:
        """00:00 aligns to both hourly and daily (hour==0, minute==0)."""
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC))
        assert mask & ALIGN_HOURLY
        assert mask & ALIGN_DAILY

    def test_naive_datetime(self) -> None:
        mask = _compute_alignment_mask(datetime(2026, 5, 1, 14, 0, 0))
        assert mask & ALIGN_HOURLY


class TestFloorToBucket:
    def test_5min_floor(self) -> None:
        dt = datetime(2026, 5, 1, 14, 3, 30, tzinfo=UTC)
        result = _floor_to_bucket(dt, "5min")
        assert result == datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)

    def test_15min_floor(self) -> None:
        dt = datetime(2026, 5, 1, 14, 17, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "15min")
        assert result == datetime(2026, 5, 1, 14, 15, 0, tzinfo=UTC)

    def test_30min_floor(self) -> None:
        dt = datetime(2026, 5, 1, 14, 35, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "30min")
        assert result == datetime(2026, 5, 1, 14, 30, 0, tzinfo=UTC)

    def test_hourly(self) -> None:
        dt = datetime(2026, 5, 1, 14, 45, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "hourly")
        assert result == datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)

    def test_daily(self) -> None:
        dt = datetime(2026, 5, 1, 14, 30, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "daily")
        assert result == datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)

    def test_weekly_monday(self) -> None:
        dt = datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)  # Friday
        result = _floor_to_bucket(dt, "weekly")
        assert result == datetime(2026, 4, 27, 0, 0, 0, tzinfo=UTC)

    def test_monthly(self) -> None:
        dt = datetime(2026, 5, 15, 14, 0, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "monthly")
        assert result == datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)

    def test_naive_datetime(self) -> None:
        dt = datetime(2026, 5, 1, 14, 30, 0)
        result = _floor_to_bucket(dt, "hourly")
        assert result.tzinfo == UTC
        assert result == datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)

    def test_invalid_bucket(self) -> None:
        with pytest.raises(ValueError):
            _floor_to_bucket(datetime(2026, 5, 1, tzinfo=UTC), "invalid")


class TestAggregateSnapshots:
    # === helpers ===
    def test_empty(self) -> None:
        assert _aggregate_snapshots([], "hourly", "total") == []

    def test_invalid_mode(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100, 200])
        with pytest.raises(ValueError):
            _aggregate_snapshots(snaps, "hourly", "bogus")

    def test_invalid_bucket(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100, 200])
        with pytest.raises(ValueError):
            _aggregate_snapshots(snaps, "bogus", "total")

    # === total mode ===
    def test_total_single(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100])
        result = _aggregate_snapshots(snaps, "hourly", "total")
        assert len(result) == 1
        assert result[0]["value"] == 100

    def test_total_hourly_last_value(self) -> None:
        snaps = _make_snaps(
            datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
            [100, 120, 140, 160],
        )
        result = _aggregate_snapshots(snaps, "hourly", "total")
        assert len(result) == 1
        assert result[0]["value"] == 160

    def test_total_daily_buckets(self) -> None:
        from datetime import timedelta

        start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
        snaps = [
            _FakeSnapshot(value=100, fetched_at=start),
            _FakeSnapshot(value=200, fetched_at=start + timedelta(days=1)),
            _FakeSnapshot(value=300, fetched_at=start + timedelta(days=1, hours=12)),
            _FakeSnapshot(value=400, fetched_at=start + timedelta(days=2)),
        ]
        result = _aggregate_snapshots(snaps, "daily", "total")
        assert len(result) == 3
        assert result[0]["value"] == 100
        assert result[1]["value"] == 300
        assert result[2]["value"] == 400

    # === delta mode — snapshots are already alignment-filtered; just diffs ===
    def test_delta_single(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100])
        assert _aggregate_snapshots(snaps, "hourly", "delta") == []

    def test_delta_hourly_aligned(self) -> None:
        """Hourly-aligned snapshots: 14:00→100, 15:00→160, 16:00→250.
        Deltas should be 60, 90."""
        from datetime import timedelta

        start = datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)
        snaps = [
            _FakeSnapshot(value=100, fetched_at=start),
            _FakeSnapshot(value=160, fetched_at=start + timedelta(hours=1)),
            _FakeSnapshot(value=250, fetched_at=start + timedelta(hours=2)),
        ]
        result = _aggregate_snapshots(snaps, "hourly", "delta")
        assert len(result) == 2
        assert result[0]["value"] == 60
        assert result[1]["value"] == 90

    def test_delta_daily_aligned(self) -> None:
        from datetime import timedelta

        start = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        snaps = [
            _FakeSnapshot(value=100, fetched_at=start),
            _FakeSnapshot(value=300, fetched_at=start + timedelta(days=1)),
            _FakeSnapshot(value=700, fetched_at=start + timedelta(days=2)),
        ]
        result = _aggregate_snapshots(snaps, "daily", "delta")
        assert len(result) == 2
        assert result[0]["value"] == 200
        assert result[1]["value"] == 400


# ── add_resolved_media tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_resolved_media_sets_metrics_last_fetched_at(session: Any) -> None:
    session.add(Guild(id=10))
    await session.flush()

    registry = MediaProviderRegistry()
    registry.register(YouTubeProvider(api_key="fake-key"))

    svc = MediaService(session=session, registry=registry)

    resolved = ResolvedMedia(
        external_id="vid_001",
        title="Test Video",
        channel_name="Test Channel",
    )

    result = await svc.add_resolved_media(
        guild_id=10,
        media_type="youtube",
        resolved=resolved,
        added_by=100,
    )
    await session.flush()

    assert result is not None
    assert result["metrics_last_fetched_at"] is not None
