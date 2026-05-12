"""Mock media providers for dev-mock mode — returns fake data without API calls."""

from __future__ import annotations

from datetime import UTC, datetime

from stankbot.services.media_providers.base import (
    MediaProvider,
    MetricDef,
    MetricResult,
    OwnerResult,
    ResolvedMedia,
)


class MockYouTubeProvider(MediaProvider):
    media_type = "youtube"
    label = "YouTube"
    icon = "\u25b6\ufe0f"
    metrics = [
        MetricDef("view_count", "Views", "number", "\U0001f441\ufe0f"),
        MetricDef("like_count", "Likes", "number", "\U0001f44d"),
        MetricDef("comment_count", "Comments", "number", "\U0001f4ac"),
    ]
    owner_metrics = [
        MetricDef("subscriber_count", "Subscribers", "number", "\U0001f4ca"),
        MetricDef("video_count", "Videos", "number", "\U0001f3ac"),
        MetricDef("total_view_count", "Total Views", "number", "\U0001f441\ufe0f"),
        MetricDef("total_like_count", "Total Likes", "number", "\U0001f44d"),
        MetricDef("total_comment_count", "Total Comments", "number", "\U0001f4ac"),
    ]

    def is_configured(self) -> bool:
        return True

    async def resolve(self, url_or_id: str) -> ResolvedMedia | None:
        vid = url_or_id.strip()[:50]
        if "youtube.com" in url_or_id or "youtu.be" in url_or_id:
            import re
            m = re.search(r"v=([\w-]{11})", url_or_id)
            if m:
                vid = m.group(1)
            else:
                m = re.search(r"youtu\.be/([\w-]{11})", url_or_id)
                if m:
                    vid = m.group(1)
        return ResolvedMedia(
            external_id=vid,
            title=f"Mock YouTube Video — {vid}",
            channel_name="Mock Channel",
            channel_id="UC_mock",
            thumbnail_url="",
            published_at=datetime(2026, 1, 15, tzinfo=UTC),
            duration_seconds=240,
        )

    async def fetch_metrics(self, external_ids: list[str]) -> list[MetricResult]:
        return [
            MetricResult(
                external_id=eid,
                values={"view_count": 12345, "like_count": 678, "comment_count": 90},
            )
            for eid in external_ids
        ]

    async def fetch_owner(self, external_id: str) -> OwnerResult | None:
        return OwnerResult(
            external_id=external_id,
            name="Mock Channel",
            external_url=f"https://youtube.com/channel/{external_id}",
            metrics={
                "subscriber_count": 1000000,
                "view_count": 50000000,
                "video_count": 200,
            },
        )

    async def health_check(self) -> bool:
        return True


class MockSpotifyProvider(MediaProvider):
    media_type = "spotify"
    label = "Spotify"
    icon = "\U0001f7e2"
    metrics = [
        MetricDef("playcount", "Play Count", "number", "\U0001f3a7"),
    ]
    owner_metrics = [
        MetricDef("follower_count", "Followers", "number", "\U0001f465"),
        MetricDef("popularity", "Popularity", "number", "\U0001f525"),
        MetricDef("total_playcount", "Total Plays", "number", "\U0001f3a7"),
    ]

    def is_configured(self) -> bool:
        return True

    async def resolve(self, url_or_id: str) -> ResolvedMedia | None:
        sid = url_or_id.strip()[:50]
        if "spotify.com" in url_or_id or "spotify:" in url_or_id:
            import re
            m = re.search(r"(?:track|album)/(\w+)", url_or_id)
            if m:
                sid = m.group(1)
            else:
                m = re.search(r"spotify:(?:track|album):(\w+)", url_or_id)
                if m:
                    sid = m.group(1)
        return ResolvedMedia(
            external_id=sid,
            title=f"Mock Spotify Track — {sid}",
            channel_name="Mock Artist",
            channel_id="mock_artist",
            thumbnail_url="",
            published_at=datetime(2026, 2, 20, tzinfo=UTC),
            duration_seconds=200,
        )

    async def fetch_metrics(self, external_ids: list[str]) -> list[MetricResult]:
        return [
            MetricResult(external_id=eid, values={"playcount": 1000000})
            for eid in external_ids
        ]

    async def fetch_owner(self, external_id: str) -> OwnerResult | None:
        return OwnerResult(
            external_id=external_id,
            name="Mock Artist",
            external_url=f"https://open.spotify.com/artist/{external_id}",
            metrics={
                "follower_count": 500000,
                "popularity": 75,
            },
        )

    async def health_check(self) -> bool:
        return True
