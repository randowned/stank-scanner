"""Unit tests for media_service._floor_to_bucket and _aggregate_snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from stankbot.services.media_service import _aggregate_snapshots, _floor_to_bucket


@dataclass
class _FakeSnapshot:
    value: int
    fetched_at: datetime


def _make_snaps(start: datetime, values: list[int], interval_mins: int = 15):
    snaps: list[_FakeSnapshot] = []
    from datetime import timedelta

    for i, v in enumerate(values):
        snaps.append(
            _FakeSnapshot(
                value=v,
                fetched_at=start + timedelta(minutes=i * interval_mins),
            )
        )
    return snaps


class TestFloorToBucket:
    def test_5min_floor(self) -> None:
        dt = datetime(2026, 5, 1, 14, 3, 30, tzinfo=UTC)
        result = _floor_to_bucket(dt, "5min")
        assert result == datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)

    def test_5min_boundary(self) -> None:
        dt = datetime(2026, 5, 1, 14, 5, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "5min")
        assert result == datetime(2026, 5, 1, 14, 5, 0, tzinfo=UTC)

    def test_15min_floor(self) -> None:
        dt = datetime(2026, 5, 1, 14, 17, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "15min")
        assert result == datetime(2026, 5, 1, 14, 15, 0, tzinfo=UTC)

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
        assert result == datetime(2026, 4, 27, 0, 0, 0, tzinfo=UTC)  # Monday

    def test_weekly_on_monday(self) -> None:
        dt = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)  # Monday
        result = _floor_to_bucket(dt, "weekly")
        assert result == datetime(2026, 5, 4, 0, 0, 0, tzinfo=UTC)

    def test_monthly(self) -> None:
        dt = datetime(2026, 5, 15, 14, 0, 0, tzinfo=UTC)
        result = _floor_to_bucket(dt, "monthly")
        assert result == datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)

    def test_naive_datetime(self) -> None:
        dt = datetime(2026, 5, 1, 14, 30, 0)  # no tzinfo
        result = _floor_to_bucket(dt, "hourly")
        assert result.tzinfo == UTC
        assert result == datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)

    def test_invalid_bucket(self) -> None:
        with pytest.raises(ValueError):
            _floor_to_bucket(datetime(2026, 5, 1, tzinfo=UTC), "invalid")


class TestAggregateSnapshots:
    def test_empty(self) -> None:
        result = _aggregate_snapshots([], "hourly", "total")
        assert result == []

    def test_single_snapshot_total(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100])
        result = _aggregate_snapshots(snaps, "hourly", "total")
        assert len(result) == 1
        assert result[0]["value"] == 100

    def test_single_snapshot_delta(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100])
        result = _aggregate_snapshots(snaps, "hourly", "delta")
        assert result == []

    def test_total_hourly_last_value(self) -> None:
        snaps = _make_snaps(
            datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
            [100, 120, 140, 160],  # 4 snapshots at 15-min intervals
        )
        result = _aggregate_snapshots(snaps, "hourly", "total")
        assert len(result) == 1  # all in same hour
        assert result[0]["value"] == 160  # last value wins

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
        assert result[0]["value"] == 100  # day 1, only one snapshot
        assert result[1]["value"] == 300  # day 2, last snapshot wins
        assert result[2]["value"] == 400  # day 3

    def test_delta_hourly_sums(self) -> None:
        snaps = _make_snaps(
            datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
            [100, 120, 140, 160, 200, 250],  # 6 snapshots at 15-min
        )
        # Deltas: 20, 20, 20, 40, 50
        # snap[0]=14:00, snap[1]=14:15, snap[2]=14:30, snap[3]=14:45, snap[4]=15:00, snap[5]=15:15
        # 14:00 bucket: deltas from 14:15, 14:30, 14:45 = 20+20+20 = 60
        # 15:00 bucket: deltas from 15:00, 15:15 = 40+50 = 90
        result = _aggregate_snapshots(snaps, "hourly", "delta")
        assert len(result) == 2
        assert result[0]["value"] == 60
        assert result[1]["value"] == 90

    def test_delta_daily_sums(self) -> None:
        from datetime import timedelta

        start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        snaps = [
            _FakeSnapshot(value=100, fetched_at=start),
            _FakeSnapshot(value=150, fetched_at=start + timedelta(hours=6)),       # delta=50 → day1
            _FakeSnapshot(value=300, fetched_at=start + timedelta(days=1)),        # delta=150 → day2
            _FakeSnapshot(value=500, fetched_at=start + timedelta(days=1, hours=6)),  # delta=200 → day2
        ]
        result = _aggregate_snapshots(snaps, "daily", "delta")
        assert len(result) == 2
        assert result[0]["value"] == 50   # day 1
        assert result[1]["value"] == 350  # day 2: 150 + 200

    def test_mixed_intervals(self) -> None:
        """Mix of 60-min and 15-min intervals; delta sum per bucket should be consistent."""
        from datetime import timedelta

        start = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
        snaps = [
            _FakeSnapshot(value=100, fetched_at=start),
            _FakeSnapshot(value=200, fetched_at=start + timedelta(days=1)),
            _FakeSnapshot(value=210, fetched_at=start + timedelta(days=1, minutes=15)),
            _FakeSnapshot(value=220, fetched_at=start + timedelta(days=1, minutes=30)),
            _FakeSnapshot(value=230, fetched_at=start + timedelta(days=1, minutes=45)),
            _FakeSnapshot(value=300, fetched_at=start + timedelta(days=2)),
        ]
        result = _aggregate_snapshots(snaps, "daily", "delta")
        # Deltas are keyed by the later snapshot's bucket:
        #  100→200 (ts=day2): delta=100 → day2
        #  200→210 (ts=day2+15min): delta=10 → day2
        #  210→220 (ts=day2+30min): delta=10 → day2
        #  220→230 (ts=day2+45min): delta=10 → day2
        #  230→300 (ts=day3): delta=70 → day3
        assert len(result) == 2  # day2, day3
        assert result[0]["value"] == 130
        assert result[1]["value"] == 70

    def test_5min_bucket(self) -> None:
        from datetime import timedelta

        start = datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)
        snaps = [
            _FakeSnapshot(value=100, fetched_at=start),
            _FakeSnapshot(value=110, fetched_at=start + timedelta(minutes=3)),  # delta=10
            _FakeSnapshot(value=115, fetched_at=start + timedelta(minutes=6)),  # delta=5, bucket 14:05
        ]
        result = _aggregate_snapshots(snaps, "5min", "delta")
        assert len(result) == 2
        # First delta (100→110) at 14:03 → floor to 14:00
        # Second delta (110→115) at 14:06 → floor to 14:05
        assert result[0]["value"] == 10  # 14:00 bucket
        assert result[1]["value"] == 5   # 14:05 bucket

    def test_invalid_mode(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100, 200])
        with pytest.raises(ValueError):
            _aggregate_snapshots(snaps, "hourly", "bogus")

    def test_invalid_bucket(self) -> None:
        snaps = _make_snaps(datetime(2026, 5, 1, 14, 0, tzinfo=UTC), [100, 200])
        with pytest.raises(ValueError):
            _aggregate_snapshots(snaps, "bogus", "total")
