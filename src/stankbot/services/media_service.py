"""Media service — CRUD, metrics, comparison, and refresh logic.

Framework-agnostic. Web routes and the scheduler both call this.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.repositories import media as media_repo
from stankbot.services.media_providers.base import MetricResult
from stankbot.services.media_providers.registry import MediaProviderRegistry

log = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug: lowercase, spaces→dashes, strip non-alnum."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\-\s]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:50]

log = logging.getLogger(__name__)


@dataclass(slots=True)
class RefreshResult:
    refreshed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MediaService:
    """Service for media CRUD + metrics operations.

    Takes a session and the provider registry. All mutations happen within
    the caller's transaction (caller manages session_scope).
    """

    session: AsyncSession
    registry: MediaProviderRegistry

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _iso(dt: datetime | None) -> str | None:
        """Serialize a datetime to an ISO-8601 string with UTC offset.

        If the datetime is naive (no tzinfo), appends ``+00:00`` so that
        JavaScript ``new Date()`` always interprets it as UTC regardless
        of the browser's local timezone.
        """
        if dt is None:
            return None
        s = dt.isoformat()
        if dt.tzinfo is None and s[-1] != "Z":
            s += "+00:00"
        return s

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add_media(
        self,
        guild_id: int,
        media_type: str,
        url_or_id: str,
        added_by: int,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        provider = self.registry.get(media_type)
        if provider is None:
            return None
        resolved = await provider.resolve(url_or_id)
        if resolved is None:
            return None
        return await self.add_resolved_media(
            guild_id=guild_id,
            media_type=media_type,
            resolved=resolved,
            added_by=added_by,
            name=name,
        )

    async def add_resolved_media(
        self,
        guild_id: int,
        media_type: str,
        resolved: Any,
        added_by: int,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        """Insert a pre-resolved media item. Caller must have already
        validated that the provider is configured and the URL resolves."""
        # Check for duplicate external_id
        if await media_repo.is_external_id_taken(
            self.session, guild_id, media_type, resolved.external_id
        ):
            return None

        name_final = str(name).strip() if name else None
        if not name_final:
            name_final = _slugify(resolved.title)[:50]
        if not name_final:
            name_final = resolved.external_id[:50]

        # Ensure unique name per media_type
        if await media_repo.is_name_taken(self.session, guild_id, media_type, name_final):
            counter = 1
            base_name = name_final[:45]
            while await media_repo.is_name_taken(
                self.session, guild_id, media_type, f"{base_name}-{counter}"
            ):
                counter += 1
            name_final = f"{base_name}-{counter}"[:50]

        item = await media_repo.add(
            self.session,
            guild_id=guild_id,
            media_type=media_type,
            external_id=resolved.external_id,
            title=resolved.title,
            channel_name=resolved.channel_name,
            channel_id=resolved.channel_id,
            thumbnail_url=resolved.thumbnail_url,
            published_at=resolved.published_at,
            duration_seconds=resolved.duration_seconds,
            added_by=added_by,
            slug=name_final,
        )
        return self._serialize_item(item)

    async def get_media_item(self, media_item_id: int) -> dict[str, Any] | None:
        item = await media_repo.get(self.session, media_item_id)
        if item is None:
            return None
        metrics = await media_repo.get_metric_cache(self.session, media_item_id)
        return self._serialize_item(item, metrics)

    async def get_media_item_by_name(
        self, guild_id: int, media_type: str, name: str
    ) -> dict[str, Any] | None:
        item = await media_repo.get_by_name(self.session, guild_id, media_type, name)
        if item is None:
            return None
        return self._serialize_item(item)

    async def list_media(
        self,
        guild_id: int,
        media_type: str | None = None,
    ) -> list[dict[str, Any]]:
        items = await media_repo.list_all(self.session, guild_id, media_type)
        item_ids = [i.id for i in items]
        metrics_by_id = await media_repo.get_metrics_for_items(self.session, item_ids)
        return [self._serialize_item(i, metrics_by_id.get(i.id, {})) for i in items]

    async def update_name(
        self, media_item_id: int, name: str | None
    ) -> dict[str, Any] | None:
        item = await media_repo.get(self.session, media_item_id)
        if item is None:
            return None

        name_final = str(name).strip() if name else None
        if not name_final:
            name_final = _slugify(item.title)[:50]
        if not name_final:
            name_final = item.external_id[:50]

        if name_final != item.name and await media_repo.is_name_taken(
            self.session, item.guild_id, item.media_type, name_final,
            exclude_id=item.id,
        ):
            counter = 1
            base_name = name_final[:45]
            while await media_repo.is_name_taken(
                self.session, item.guild_id, item.media_type,
                f"{base_name}-{counter}", exclude_id=item.id,
            ):
                counter += 1
            name_final = f"{base_name}-{counter}"[:50]

        item.name = name_final
        return self._serialize_item(item)

    async def delete_media(self, media_item_id: int) -> bool:
        return await media_repo.delete_media(self.session, media_item_id)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def get_metrics_history(
        self,
        media_item_id: int,
        metric_key: str,
        window_days: int = 30,
        window_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        since = None
        if window_hours is not None and window_hours > 0:
            since = datetime.now(UTC) - timedelta(hours=window_hours)
        elif window_days > 0:
            since = datetime.now(UTC) - timedelta(days=window_days)
        snapshots = await media_repo.get_metric_snapshots(
            self.session, media_item_id, metric_key, since
        )
        return [
            {"fetched_at": s.fetched_at.isoformat(), "value": s.value}
            for s in snapshots
        ]

    async def get_comparison_data(
        self,
        media_item_ids: list[int],
        metric_key: str,
        window_days: int = 30,
        align_release: bool = False,
        delta: bool = True,
    ) -> dict[str, Any]:
        if align_release:
            return await self._comparison_aligned(media_item_ids, metric_key, window_days, delta=delta)

        since = None
        if window_days > 0:
            since = datetime.now(UTC) - timedelta(days=window_days)

        snapshots_by_id = await media_repo.get_comparison_snapshots(
            self.session, media_item_ids, metric_key, since
        )

        items: list[dict[str, Any]] = []
        metric_def = None
        for mid in media_item_ids:
            item = await media_repo.get(self.session, mid)
            if item is None:
                continue
            snaps = snapshots_by_id.get(mid, [])
            raw_points = [
                {"x": s.fetched_at.isoformat(), "y": s.value}
                for s in snaps
            ]
            if delta and len(raw_points) >= 2:
                prev = raw_points[0]["y"]
                for _i, pt in enumerate(raw_points):
                    cur = pt["y"]
                    pt["y"] = cur - prev  # type: ignore[operator]
                    prev = cur
                raw_points[0]["y"] = 0
            elif delta:
                for pt in raw_points:
                    pt["y"] = 0

            items.append({
                "media_item_id": mid,
                "media_type": item.media_type,
                "title": item.title,
                "points": raw_points,
            })

            if metric_def is None:
                provider = self.registry.get(item.media_type)
                if provider:
                    for m in provider.metrics:
                        if m.key == metric_key:
                            metric_def = {"key": m.key, "label": m.label, "format": m.format}
                            break

        return {"metric": metric_def, "series": items, "aligned": False}

    async def _comparison_aligned(
        self,
        media_item_ids: list[int],
        metric_key: str,
        window_days: int = 90,
        delta: bool = True,
    ) -> dict[str, Any]:
        snapshots_by_id = await media_repo.get_comparison_snapshots(
            self.session, media_item_ids, metric_key, None
        )

        items: list[dict[str, Any]] = []
        metric_def = None
        for mid in media_item_ids:
            item = await media_repo.get(self.session, mid)
            if item is None:
                continue
            snaps = snapshots_by_id.get(mid, [])
            pub_date = item.published_at
            points: list[dict[str, object]] = []
            for s in snaps:
                if pub_date is None:
                    continue
                day_offset = (s.fetched_at - pub_date).days
                if day_offset < 0:
                    continue
                if window_days > 0 and day_offset > window_days:
                    continue
                points.append({"x": day_offset, "y": s.value})
            if points:
                if delta and len(points) >= 2:
                    prev = points[0]["y"]
                    for _i, pt in enumerate(points):
                        cur = pt["y"]
                        pt["y"] = cur - prev  # type: ignore[operator]
                        prev = cur
                    points[0]["y"] = 0
                elif delta:
                    for pt in points:
                        pt["y"] = 0

                items.append({
                    "media_item_id": mid,
                    "media_type": item.media_type,
                    "title": item.title,
                    "points": points,
                })

                if metric_def is None:
                    provider = self.registry.get(item.media_type)
                    if provider:
                        for m in provider.metrics:
                            if m.key == metric_key:
                                metric_def = {"key": m.key, "label": m.label, "format": m.format}
                                break

        return {"metric": metric_def, "series": items, "aligned": True}

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    async def refresh_all(self, guild_id: int) -> RefreshResult:
        result = RefreshResult()
        for provider in self.registry.enabled():
            items = await media_repo.list_all(self.session, guild_id, provider.media_type)
            if not items:
                continue
            external_ids = [i.external_id for i in items]
            id_to_item = {i.external_id: i for i in items}
            metrics_list = await provider.fetch_metrics(external_ids)
            now = datetime.now(UTC)
            for mr in metrics_list:
                item = id_to_item.get(mr.external_id)
                if item is None:
                    continue
                if mr.error:
                    result.failed += 1
                    result.errors.append(f"{item.title}: {mr.error}")
                    continue
                for metric_key, value in mr.values.items():
                    await media_repo.upsert_metric_cache(
                        self.session, item.id, metric_key, value, now
                    )
                    await media_repo.insert_metric_snapshot(
                        self.session, item.id, metric_key, value, now
                    )
                item.metrics_last_fetched_at = now
                result.refreshed += 1
        return result

    async def refresh_single(self, media_item_id: int) -> MetricResult | None:
        item = await media_repo.get(self.session, media_item_id)
        if item is None:
            return None

        provider = self.registry.get(item.media_type)
        if provider is None:
            return MetricResult(external_id=item.external_id, error="provider_not_found")

        results = await provider.fetch_metrics([item.external_id])
        if not results:
            return MetricResult(external_id=item.external_id, error="no_response")

        mr = results[0]
        if mr.error:
            return mr

        now = datetime.now(UTC)
        for metric_key, value in mr.values.items():
            await media_repo.upsert_metric_cache(
                self.session, item.id, metric_key, value, now
            )
            await media_repo.insert_metric_snapshot(
                self.session, item.id, metric_key, value, now
            )

        item.metrics_last_fetched_at = now
        return mr

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize_item(
        self,
        item: Any,
        metrics: dict[str, dict[str, int | str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "guild_id": str(item.guild_id),
            "media_type": item.media_type,
            "external_id": item.external_id,
            "title": item.title,
            "channel_name": item.channel_name,
            "channel_id": item.channel_id,
            "thumbnail_url": item.thumbnail_url,
            "published_at": self._iso(item.published_at),
            "duration_seconds": item.duration_seconds,
            "added_by": str(item.added_by),
            "name": item.name,
            "metrics": metrics or {},
            "metrics_last_fetched_at": self._iso(item.metrics_last_fetched_at),
            "created_at": self._iso(item.created_at),
            "updated_at": self._iso(item.updated_at),
        }
