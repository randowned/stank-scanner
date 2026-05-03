"""Unit tests for cleanup_chart_cache — deletes stale chart PNGs from disk."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from stankbot.web.routes import media_api


def _touch(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG header bytes; content doesn't matter


class TestCleanupChartCache:
    def test_deletes_only_stale_files(self, tmp_path: Path) -> None:
        now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
        fresh_ts = int((now - timedelta(hours=1)).timestamp())
        stale_ts = int((now - timedelta(hours=48)).timestamp())

        fresh = tmp_path / f"42_view_count_d7_{fresh_ts}_total.png"
        stale = tmp_path / f"42_view_count_d7_{stale_ts}_total.png"
        _touch(fresh)
        _touch(stale)

        with patch.object(media_api, "CHART_CACHE_DIR", tmp_path):
            deleted = media_api.cleanup_chart_cache(now=now)

        assert deleted == 1
        assert fresh.exists()
        assert not stale.exists()

    def test_skips_files_without_timestamp(self, tmp_path: Path) -> None:
        now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
        weird = tmp_path / "no_timestamp_here.png"
        _touch(weird)

        with patch.object(media_api, "CHART_CACHE_DIR", tmp_path):
            deleted = media_api.cleanup_chart_cache(now=now)

        assert deleted == 0
        assert weird.exists()

    def test_returns_zero_when_dir_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        with patch.object(media_api, "CHART_CACHE_DIR", missing):
            assert media_api.cleanup_chart_cache() == 0

    def test_ignores_non_png_files(self, tmp_path: Path) -> None:
        now = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)
        stale_ts = int((now - timedelta(hours=48)).timestamp())
        stale_txt = tmp_path / f"42_view_count_d7_{stale_ts}_total.txt"
        _touch(stale_txt)

        with patch.object(media_api, "CHART_CACHE_DIR", tmp_path):
            deleted = media_api.cleanup_chart_cache(now=now)

        assert deleted == 0
        assert stale_txt.exists()
