from __future__ import annotations

from datetime import UTC, datetime

from stankbot.utils.time_utils import (
    humanize_duration,
    next_reset_at,
    utc_isoformat,
    utc_timestamp,
)


def test_humanize_zero() -> None:
    assert humanize_duration(0) == "0s"
    assert humanize_duration(-5) == "0s"


def test_humanize_seconds_only_when_under_a_minute() -> None:
    assert humanize_duration(45) == "45s"


def test_humanize_keeps_seconds_with_minutes() -> None:
    assert humanize_duration(150) == "2m 30s"
    assert humanize_duration(120) == "2m"


def test_humanize_drops_seconds_once_hours_present() -> None:
    assert humanize_duration(3600 + 45) == "1h"
    assert humanize_duration(3600 + 120 + 5) == "1h 2m"


def test_humanize_hours_and_minutes() -> None:
    assert humanize_duration(2 * 3600 + 14 * 60) == "2h 14m"


def test_humanize_days() -> None:
    assert humanize_duration(3 * 86_400 + 5 * 3600) == "3d 5h"


def test_next_reset_picks_today_when_future_hour_available() -> None:
    now = datetime(2026, 4, 19, 6, 0, tzinfo=UTC)
    result = next_reset_at([7, 15, 23], now=now)
    assert result == datetime(2026, 4, 19, 7, 0, tzinfo=UTC)


def test_next_reset_skips_past_hours_same_day() -> None:
    now = datetime(2026, 4, 19, 10, 0, tzinfo=UTC)
    result = next_reset_at([7, 15, 23], now=now)
    assert result == datetime(2026, 4, 19, 15, 0, tzinfo=UTC)


def test_next_reset_rolls_to_tomorrow_after_all_hours_pass() -> None:
    now = datetime(2026, 4, 19, 23, 30, tzinfo=UTC)
    result = next_reset_at([7, 15, 23], now=now)
    assert result == datetime(2026, 4, 20, 7, 0, tzinfo=UTC)


class TestUtcIsoformat:
    def test_none_returns_none(self) -> None:
        assert utc_isoformat(None) is None

    def test_aware_retains_offset(self) -> None:
        result = utc_isoformat(datetime(2026, 4, 30, 2, 5, 22, tzinfo=UTC))
        assert result == "2026-04-30T02:05:22+00:00"

    def test_naive_gets_utc_offset(self) -> None:
        result = utc_isoformat(datetime(2026, 4, 30, 2, 5, 22))
        assert result == "2026-04-30T02:05:22+00:00"

    def test_microseconds_preserved(self) -> None:
        result = utc_isoformat(datetime(2026, 4, 30, 2, 5, 22, 123456, tzinfo=UTC))
        assert "123456" in result
        assert result.endswith("+00:00")


class TestUtcTimestamp:
    def test_aware_returns_correct_timestamp(self) -> None:
        dt = datetime(2026, 4, 30, 2, 5, 22, tzinfo=UTC)
        expected = dt.timestamp()
        assert utc_timestamp(dt) == expected

    def test_naive_returns_same_as_aware(self) -> None:
        naive = datetime(2026, 4, 30, 2, 5, 22)
        aware = naive.replace(tzinfo=UTC)
        assert utc_timestamp(naive) == aware.timestamp()

    def test_epoch(self) -> None:
        assert utc_timestamp(datetime(1970, 1, 1, tzinfo=UTC)) == 0.0

    def test_negative_timestamp(self) -> None:
        dt = datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC)
        assert utc_timestamp(dt) == -1.0
