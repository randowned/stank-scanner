"""YouTube provider — YouTube Data API v3 integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from .base import MediaProvider, MetricDef, MetricResult, OwnerResult, ResolvedMedia

log = logging.getLogger(__name__)

_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})",
    re.IGNORECASE,
)
_YOUTUBE_ID_RE = re.compile(r"^[\w-]{11}$")

_VIDEO_PARTS = "snippet,statistics,contentDetails"
_API_BASE = "https://www.googleapis.com/youtube/v3/videos"
_CHANNELS_API_BASE = "https://www.googleapis.com/youtube/v3/channels"


class QuotaExceededError(Exception):
    """YouTube API quota has been exhausted."""


class YouTubeProvider(MediaProvider):
    media_type = "youtube"
    label = "YouTube"
    icon = "▶️"
    metrics = [
        MetricDef("view_count", "Views", "number", "👁️"),
        MetricDef("like_count", "Likes", "number", "👍"),
        MetricDef("comment_count", "Comments", "number", "💬"),
    ]

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def extract_video_id(url_or_id: str) -> str | None:
        m = _YOUTUBE_URL_RE.search(url_or_id)
        if m:
            return m.group(1)
        if _YOUTUBE_ID_RE.match(url_or_id.strip()):
            return url_or_id.strip()
        return None

    @staticmethod
    def parse_duration(iso8601: str) -> int | None:
        """PT4M13S → 253, PT1H2M3S → 3723."""
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso8601)
        if not m:
            return None
        h = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        return h * 3600 + mins * 60 + s

    async def resolve(self, url_or_id: str) -> ResolvedMedia | None:
        video_id = self.extract_video_id(url_or_id)
        if not video_id:
            return None
        try:
            results = await self._fetch_resolved_batch([video_id])
        except QuotaExceededError:
            log.warning("YouTube quota exceeded while resolving video_id=%s", video_id)
            return None
        return results.get(video_id)

    async def fetch_metrics(self, external_ids: list[str]) -> list[MetricResult]:
        results: list[MetricResult] = []
        for i in range(0, len(external_ids), 50):
            batch = list(external_ids[i : i + 50])
            batch_results = await self._fetch_metric_batch(batch)
            for vid in batch:
                item = batch_results.get(vid)
                if item is None:
                    results.append(MetricResult(external_id=vid, error="not_found"))
                else:
                    results.append(item)
        return results

    async def _call_api(self, video_ids: list[str]) -> dict[str, Any]:
        """Call YouTube API for a batch of video IDs. Returns parsed JSON or empty dict."""
        if not self._api_key:
            return {}

        ids = ",".join(video_ids)
        url = f"{_API_BASE}?part={_VIDEO_PARTS}&id={ids}&key={self._api_key}"

        client = self._get_client()
        backoff = 1.0

        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=15.0)
                if resp.status_code == 403:
                    body = resp.text
                    if "quotaExceeded" in body:
                        raise QuotaExceededError("YouTube API quota exceeded")
                    log.warning("YouTube API 403 for batch: %s", body[:200])
                    return {}
                if resp.status_code == 404:
                    return {}
                if resp.status_code != 200:
                    log.warning(
                        "YouTube API returned %d for batch (attempt %d)",
                        resp.status_code,
                        attempt + 1,
                    )
                    if attempt < 2:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30)
                        continue
                    return {}
                return dict(resp.json())
            except httpx.HTTPError as exc:
                log.warning("YouTube API request failed (attempt %d): %s", attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                return {}
        return {}

    async def _fetch_resolved_batch(self, video_ids: list[str]) -> dict[str, ResolvedMedia]:
        """Fetch video metadata (title, channel, thumbnails, etc.)."""
        data = await self._call_api(video_ids)
        return self._parse_resolved(data)

    async def _fetch_metric_batch(self, video_ids: list[str]) -> dict[str, MetricResult]:
        """Fetch video statistics (views, likes, comments)."""
        data = await self._call_api(video_ids)
        return self._parse_metrics(data)

    def _parse_resolved(self, data: dict[str, Any]) -> dict[str, ResolvedMedia]:
        result: dict[str, ResolvedMedia] = {}
        for item in data.get("items", []):
            vid = item.get("id", "")
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})

            pub_str = snippet.get("publishedAt", "")
            pub = None
            if pub_str:
                with contextlib.suppress(ValueError, TypeError):
                    pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))

            dur = self.parse_duration(content_details.get("duration", ""))

            result[vid] = ResolvedMedia(
                external_id=vid,
                title=snippet.get("title", ""),
                channel_name=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                thumbnail_url=self._best_thumbnail(snippet.get("thumbnails", {})),
                published_at=pub,
                duration_seconds=dur,
            )
        return result

    def _parse_metrics(self, data: dict[str, Any]) -> dict[str, MetricResult]:
        result: dict[str, MetricResult] = {}
        for item in data.get("items", []):
            vid = item.get("id", "")
            statistics = item.get("statistics", {})

            try:
                view_count = int(statistics.get("viewCount", "0"))
            except (ValueError, TypeError):
                view_count = 0
            try:
                like_count = int(statistics.get("likeCount", "0"))
            except (ValueError, TypeError):
                like_count = 0
            try:
                comment_count = int(statistics.get("commentCount", "0"))
            except (ValueError, TypeError):
                comment_count = 0

            result[vid] = MetricResult(
                external_id=vid,
                values={
                    "view_count": view_count,
                    "like_count": like_count,
                    "comment_count": comment_count,
                },
            )
        return result

    @staticmethod
    def _best_thumbnail(thumbnails: dict[str, dict[str, str]]) -> str | None:
        for quality in ("maxres", "standard", "high", "medium", "default"):
            t = thumbnails.get(quality, {})
            url: str | None = t.get("url")
            if url:
                return url
        return None

    async def fetch_owner(self, external_id: str) -> OwnerResult | None:
        if not self._api_key or not external_id:
            return None

        url = f"{_CHANNELS_API_BASE}?part=snippet,statistics&id={external_id}&key={self._api_key}"
        client = self._get_client()

        backoff = 1.0
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=15.0)
                if resp.status_code == 403:
                    body = resp.text
                    if "quotaExceeded" in body:
                        raise QuotaExceededError("YouTube API quota exceeded")
                    log.warning("YouTube channels API 403: %s", body[:200])
                    return None
                if resp.status_code != 200:
                    if attempt < 2:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30)
                        continue
                    return None
                data: dict[str, Any] = resp.json()
                items = data.get("items", [])
                if not items:
                    return None
                channel = items[0]
                snippet = channel.get("snippet", {})
                stats: dict[str, Any] = channel.get("statistics", {})

                def _int_from(st: dict[str, Any], key: str, default: int = 0) -> int:
                    try:
                        return int(st.get(key, default))
                    except (ValueError, TypeError):
                        return default

                return OwnerResult(
                    external_id=external_id,
                    name=snippet.get("title", ""),
                    external_url=f"https://youtube.com/channel/{external_id}",
                    thumbnail_url=self._best_thumbnail(snippet.get("thumbnails", {})),
                    metrics={
                        "subscriber_count": _int_from(stats, "subscriberCount"),
                        "view_count": _int_from(stats, "viewCount"),
                        "video_count": _int_from(stats, "videoCount"),
                    },
                )
            except httpx.HTTPError as exc:
                log.warning("YouTube channels API request failed (attempt %d): %s", attempt + 1, exc)
                if attempt < 2:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                return None
        return None

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            client = self._get_client()
            url = f"{_API_BASE}?part=id&id=dQw4w9WgXcQ&key={self._api_key}"
            resp = await client.get(url, timeout=10.0)
            return resp.status_code in (200, 404)  # 404 = valid key, video not found
        except Exception:
            return False
