"""Unit tests for media milestone detection — thresholds, crossing, next-milestone."""

from __future__ import annotations

from stankbot.services.media_service import (
    MILESTONE_THRESHOLDS,
    MilestoneInfo,
    RefreshResult,
    get_crossed_milestones,
    next_milestone,
)


class TestMilestoneThresholds:
    """Verify the 63-threshold list is ordered and complete."""

    def test_count_is_63(self) -> None:
        assert len(MILESTONE_THRESHOLDS) == 63

    def test_first_is_1m(self) -> None:
        assert MILESTONE_THRESHOLDS[0] == 1_000_000

    def test_last_is_1b(self) -> None:
        assert MILESTONE_THRESHOLDS[-1] == 1_000_000_000

    def test_sorted(self) -> None:
        assert MILESTONE_THRESHOLDS == sorted(MILESTONE_THRESHOLDS)

    def test_starts_every_1m_then_jumps(self) -> None:
        first_50 = MILESTONE_THRESHOLDS[:50]
        for idx, m in enumerate(first_50):
            assert m == (idx + 1) * 1_000_000
        assert MILESTONE_THRESHOLDS[50] == 75_000_000
        assert MILESTONE_THRESHOLDS[51] == 100_000_000
        assert MILESTONE_THRESHOLDS[52] == 150_000_000


class TestGetCrossedMilestones:
    """Test threshold-crossing detection between old and new values."""

    def test_no_crossing_when_equal(self) -> None:
        assert get_crossed_milestones(0, 0) == []

    def test_no_crossing_when_regressing(self) -> None:
        assert get_crossed_milestones(5_000_000, 3_000_000) == []

    def test_no_milestone_below_1m(self) -> None:
        assert get_crossed_milestones(0, 999_999) == []

    def test_single_crossing_1m(self) -> None:
        assert get_crossed_milestones(0, 1_000_000) == [1_000_000]

    def test_single_crossing_10m(self) -> None:
        assert get_crossed_milestones(9_500_000, 10_000_000) == [10_000_000]

    def test_exact_at_threshold_no_twice(self) -> None:
        """Already at 1M, stays at 1M — should not register."""
        assert get_crossed_milestones(1_000_000, 1_000_000) == []

    def test_cross_exact_boundary(self) -> None:
        """Cross exactly on the boundary value."""
        assert get_crossed_milestones(999_999, 1_000_000) == [1_000_000]

    def test_multiple_crossings_in_one_jump(self) -> None:
        """0 → 3M should cross 1M, 2M, 3M (3M is also a threshold)."""
        assert get_crossed_milestones(0, 3_000_000) == [1_000_000, 2_000_000, 3_000_000]

    def test_multiple_crossings_with_partial_start(self) -> None:
        """1.5M → 4.5M should cross 2M, 3M, 4M."""
        assert get_crossed_milestones(1_500_000, 4_500_000) == [
            2_000_000, 3_000_000, 4_000_000,
        ]

    def test_cross_75m(self) -> None:
        assert get_crossed_milestones(50_000_000, 75_000_000) == [75_000_000]

    def test_cross_100m(self) -> None:
        assert get_crossed_milestones(75_000_000, 100_000_000) == [100_000_000]

    def test_cross_1b(self) -> None:
        assert get_crossed_milestones(900_000_000, 1_000_000_000) == [1_000_000_000]

    def test_above_1b_no_milestones(self) -> None:
        assert get_crossed_milestones(1_000_000_000, 1_500_000_000) == []

    def test_just_over_1m(self) -> None:
        assert get_crossed_milestones(0, 1_000_001) == [1_000_000]


class TestNextMilestone:
    """Test computing the next milestone above a given value."""

    def test_from_zero(self) -> None:
        assert next_milestone(0) == 1_000_000

    def test_from_500k(self) -> None:
        assert next_milestone(500_000) == 1_000_000

    def test_from_5m(self) -> None:
        assert next_milestone(5_000_000) == 6_000_000

    def test_from_50m(self) -> None:
        assert next_milestone(50_000_000) == 75_000_000

    def test_from_100m(self) -> None:
        assert next_milestone(100_000_000) == 150_000_000

    def test_from_1b(self) -> None:
        assert next_milestone(1_000_000_000) is None

    def test_from_past_1b(self) -> None:
        assert next_milestone(2_000_000_000) is None

    def test_from_just_before_threshold(self) -> None:
        assert next_milestone(999_999) == 1_000_000


class TestMilestoneInfo:
    """Verify the dataclass carries all fields needed for embed construction."""

    def test_minimal_info(self) -> None:
        mi = MilestoneInfo(
            media_item_id=42,
            media_type="youtube",
            metric_key="view_count",
            milestone_value=1_000_000,
            new_value=1_000_001,
            title="Test Video",
            channel_name="Test Channel",
            thumbnail_url="https://example.com/thumb.jpg",
            name="test-video",
            external_id="abc123",
        )
        assert mi.media_item_id == 42
        assert mi.media_type == "youtube"
        assert mi.metric_key == "view_count"
        assert mi.milestone_value == 1_000_000
        assert mi.new_value == 1_000_001
        assert mi.title == "Test Video"
        assert mi.channel_name == "Test Channel"
        assert mi.thumbnail_url == "https://example.com/thumb.jpg"
        assert mi.name == "test-video"
        assert mi.external_id == "abc123"


class TestRefreshResult:
    """Verify RefreshResult includes the milestones field."""

    def test_default_empty(self) -> None:
        rr = RefreshResult()
        assert rr.refreshed == 0
        assert rr.failed == 0
        assert rr.errors == []
        assert rr.milestones == []

    def test_can_append_milestones(self) -> None:
        rr = RefreshResult(refreshed=3, failed=1, errors=["err"])
        rr.milestones.append(
            MilestoneInfo(
                media_item_id=1, media_type="youtube", metric_key="view_count",
                milestone_value=1_000_000, new_value=1_000_001, title="t",
                channel_name="c", thumbnail_url=None, name="n", external_id="x",
            )
        )
        assert len(rr.milestones) == 1
        assert rr.milestones[0].milestone_value == 1_000_000
