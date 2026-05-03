"""Unit tests for chart_renderer.py — Pillow-based media metric chart images."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image

from stankbot.services.chart_renderer import (
    _format_number,
    _nice_range,
    _save_bytes,
    render_media_chart,
)


@dataclass
class _FakeSnapshot:
    """Minimal stub with the same interface as MetricSnapshot."""
    value: int
    fetched_at: datetime


def _make_snapshots(
    base_value: int = 1000,
    count: int = 5,
    interval_hours: int = 1,
    start: datetime | None = None,
) -> list:
    if start is None:
        start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    result = []
    for i in range(count):
        ts = start + timedelta(hours=i * interval_hours)
        result.append(_FakeSnapshot(value=base_value + i * 100, fetched_at=ts))
    return result


class TestFormatNumber:
    def test_billions(self) -> None:
        assert _format_number(1_500_000_000) == "1.5B"

    def test_millions(self) -> None:
        assert _format_number(2_300_000) == "2.3M"

    def test_thousands(self) -> None:
        assert _format_number(4_200) == "4.2K"

    def test_small_integer(self) -> None:
        assert _format_number(42) == "42"

    def test_zero(self) -> None:
        assert _format_number(0) == "0"

    def test_float_small(self) -> None:
        assert _format_number(3.5) == "3.5"


class TestNiceRange:
    def test_typical_range(self) -> None:
        floor, ceil, lines = _nice_range(100, 500)
        assert floor <= 100
        assert ceil >= 500
        assert 3 <= lines <= 8

    def test_zero_span(self) -> None:
        floor, ceil, lines = _nice_range(50, 50)
        assert floor < 50 < ceil
        assert lines > 0

    def test_small_range(self) -> None:
        floor, ceil, lines = _nice_range(10, 12)
        assert floor <= 10
        assert ceil >= 12
        assert lines > 0


class TestSaveBytes:
    def test_returns_png_bytes(self) -> None:
        img = Image.new("RGB", (10, 10), "#000")
        data = _save_bytes(img)
        assert isinstance(data, bytes)
        assert len(data) > 0
        # Should be valid PNG
        parsed = Image.open(BytesIO(data))
        assert parsed.size == (10, 10)


class TestRenderMediaChart:
    def test_returns_bytes(self) -> None:
        snaps = _make_snapshots()
        buf = render_media_chart(
            snapshots=snaps,
            title="Test",
            metric_label="Views",
            duration_hours=4,
        )
        assert isinstance(buf, bytes)
        assert len(buf) > 1000  # should be a substantial PNG

    def test_valid_png(self) -> None:
        snaps = _make_snapshots()
        buf = render_media_chart(
            snapshots=snaps,
            title="Test",
            metric_label="Views",
            duration_hours=4,
        )
        img = Image.open(BytesIO(buf))
        assert img.size == (1200, 675)
        assert img.mode == "RGB"

    def test_empty_snapshots(self) -> None:
        """Empty list should not crash — returns a placeholder image."""
        buf = render_media_chart(
            snapshots=[],
            title="Empty",
            metric_label="Views",
            duration_hours=0,
        )
        assert isinstance(buf, bytes)
        assert len(buf) > 0

    def test_single_snapshot(self) -> None:
        """Single snapshot should not crash (no line to draw)."""
        snaps = _make_snapshots(count=1)
        buf = render_media_chart(
            snapshots=snaps,
            title="Single",
            metric_label="Views",
            duration_hours=0,
        )
        assert isinstance(buf, bytes)

    def test_many_snapshots(self) -> None:
        """48-hour span with hourly snapshots."""
        snaps = _make_snapshots(count=48, interval_hours=1)
        buf = render_media_chart(
            snapshots=snaps,
            title="Many Points",
            metric_label="Views",
            duration_hours=48,
        )
        assert isinstance(buf, bytes)

    def test_large_values(self) -> None:
        """Values in the millions should format correctly on Y-axis."""
        snaps = [
            _FakeSnapshot(value=1_500_000, fetched_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC)),
            _FakeSnapshot(value=2_300_000, fetched_at=datetime(2026, 5, 1, 18, 0, tzinfo=UTC)),
            _FakeSnapshot(value=5_000_000, fetched_at=datetime(2026, 5, 2, 0, 0, tzinfo=UTC)),
        ]
        buf = render_media_chart(
            snapshots=snaps,
            title="Millions",
            metric_label="Views",
            duration_hours=12,
        )
        assert isinstance(buf, bytes)

    def test_sub_day_span_ticks(self) -> None:
        """2-hour span should generate hour/minute ticks without crashing."""
        snaps = _make_snapshots(count=3, interval_hours=1)
        buf = render_media_chart(
            snapshots=snaps,
            title="Sub-day",
            metric_label="Views",
            duration_hours=2,
        )
        assert isinstance(buf, bytes)

    def test_multi_day_span_date_labels(self) -> None:
        """Multi-day span should generate date labels without crashing."""
        snaps = _make_snapshots(count=7, interval_hours=24)
        buf = render_media_chart(
            snapshots=snaps,
            title="Multi-day",
            metric_label="Views",
            duration_hours=144,
        )
        assert isinstance(buf, bytes)
