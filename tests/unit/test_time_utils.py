from __future__ import annotations

from datetime import UTC, datetime

from stankbot.utils.time_utils import humanize_duration, next_reset_at


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
