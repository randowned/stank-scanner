"""Media service — CRUD, metrics, comparison, and refresh logic.

Framework-agnostic. Web routes and the scheduler both call this.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import MetricSnapshot
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


_VALID_AGGREGATIONS = {"5min", "15min", "30min", "hourly", "daily", "weekly", "monthly"}

# Alignment bitmask — each snapshot carries a mask of which calendar boundaries
# it aligns to.  Used to select exactly-aligned snapshots for delta aggregation
# without any client-side bucketing or summing.
ALIGN_5MIN    = 1 << 0   # 1
ALIGN_15MIN   = 1 << 1   # 2
ALIGN_30MIN   = 1 << 2   # 4
ALIGN_HOURLY  = 1 << 3   # 8
ALIGN_DAILY   = 1 << 4   # 16
ALIGN_WEEKLY  = 1 << 5   # 32
ALIGN_MONTHLY = 1 << 6   # 64

_ALIGN_BIT: dict[str, int] = {
    "5min": ALIGN_5MIN, "15min": ALIGN_15MIN, "30min": ALIGN_30MIN,
    "hourly": ALIGN_HOURLY, "daily": ALIGN_DAILY,
    "weekly": ALIGN_WEEKLY, "monthly": ALIGN_MONTHLY,
}


def _compute_alignment_mask(dt: datetime) -> int:
    """Return bitmask of calendar boundaries this timestamp aligns to.

    Seconds and microseconds are ignored — API latency can drift by
    several seconds without changing the minute-level alignment.
    """
    mask = 0
    total_minutes = dt.hour * 60 + dt.minute
    if total_minutes % 5 == 0:
        mask |= ALIGN_5MIN
    if total_minutes % 15 == 0:
        mask |= ALIGN_15MIN
    if total_minutes % 30 == 0:
        mask |= ALIGN_30MIN
    if dt.minute == 0:
        mask |= ALIGN_HOURLY
        if dt.hour == 0:
            mask |= ALIGN_DAILY
            if dt.weekday() == 0:
                mask |= ALIGN_WEEKLY
            if dt.day == 1:
                mask |= ALIGN_MONTHLY
    return mask


def _floor_to_bucket(dt: datetime, bucket: str) -> datetime:
    """Floor a datetime to the start of its calendar bucket (UTC).

    Calendar-aligned: 5min/15min/hourly snap to clock boundaries,
    daily snaps to midnight, weekly to Monday midnight, monthly to 1st.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if bucket == "5min":
        total_minutes = dt.hour * 60 + dt.minute
        floored = total_minutes // 5 * 5
        return dt.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)
    if bucket == "15min":
        total_minutes = dt.hour * 60 + dt.minute
        floored = total_minutes // 15 * 15
        return dt.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)
    if bucket == "30min":
        total_minutes = dt.hour * 60 + dt.minute
        floored = total_minutes // 30 * 30
        return dt.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)
    if bucket == "hourly":
        return dt.replace(minute=0, second=0, microsecond=0)
    if bucket == "daily":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "weekly":
        days_since_monday = dt.weekday()
        return (dt - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "monthly":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unknown aggregation bucket: {bucket}")


def _aggregate_snapshots(
    snapshots: list[Any],  # MetricSnapshot-like with .value and .fetched_at
    bucket: str,
    mode: str,
) -> list[dict[str, Any]]:
    """Aggregate snapshots into time buckets.

    Snaps are already filtered by alignment_bit (done at the query level),
    so delta mode just diffs consecutive aligned snapshots — no bucketing
    or summing required.  Total mode floors each snapshot to its bucket
    start and takes the last value per bucket.
    """
    if bucket not in _VALID_AGGREGATIONS:
        raise ValueError(f"Invalid aggregation bucket: {bucket}")
    if mode not in ("total", "delta"):
        raise ValueError(f"Invalid mode: {mode}")
    if not snapshots:
        return []

    normalized: list[tuple[datetime, int]] = []
    for s in snapshots:
        dt = s.fetched_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        normalized.append((dt, s.value))

    if mode == "total":
        buckets: dict[datetime, int] = {}
        bucket_order: list[datetime] = []
        for dt, val in normalized:
            key = _floor_to_bucket(dt, bucket)
            if key not in buckets:
                bucket_order.append(key)
            buckets[key] = val  # last value in bucket wins (cumulative)
        return [
            {"fetched_at": key.isoformat(), "value": buckets[key]}
            for key in bucket_order
        ]

    # delta mode: snapshots are already alignment-filtered — just diff
    if len(normalized) < 2:
        return []

    result: list[dict[str, Any]] = []
    for i in range(1, len(normalized)):
        cur_dt, cur_val = normalized[i]
        _prev_dt, prev_val = normalized[i - 1]
        result.append({
            "fetched_at": cur_dt.isoformat(),
            "value": cur_val - prev_val,
        })
    return result


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

    @staticmethod
    def _serialize_ts(dt: datetime) -> str:
        """Serialize a non-null datetime to an ISO-8601 string guaranteed UTC.

        Same normalisation as _iso but for the non-optional timestamp case.
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()

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
            name=name_final,
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
        aggregation: str | None = None,
        mode: str = "total",
    ) -> list[dict[str, Any]]:
        since = None
        if window_hours is not None and window_hours > 0:
            since = datetime.now(UTC) - timedelta(hours=window_hours)
        elif window_days > 0:
            since = datetime.now(UTC) - timedelta(days=window_days)

        alignment_bit: int | None = _ALIGN_BIT.get(aggregation) if aggregation else None

        snapshots = await media_repo.get_metric_snapshots(
            self.session, media_item_id, metric_key, since,
            alignment_bit=alignment_bit,
        )
        if aggregation:
            return _aggregate_snapshots(snapshots, aggregation, mode)
        return [
            {"fetched_at": self._serialize_ts(s.fetched_at), "value": s.value}
            for s in snapshots
        ]

    async def get_comparison_data(
        self,
        media_item_ids: list[int],
        metric_key: str,
        window_days: int = 30,
        window_hours: int | None = None,
        align_release: bool = False,
        delta: bool = True,
        aggregation: str | None = None,
    ) -> dict[str, Any]:
        if align_release:
            return await self._comparison_aligned(media_item_ids, metric_key, window_days, delta=delta, aggregation=aggregation)

        since = None
        if window_hours is not None and window_hours > 0:
            since = datetime.now(UTC) - timedelta(hours=window_hours)
        elif window_days > 0:
            since = datetime.now(UTC) - timedelta(days=window_days)

        alignment_bit: int | None = _ALIGN_BIT.get(aggregation) if aggregation else None

        snapshots_by_id = await media_repo.get_comparison_snapshots(
            self.session, media_item_ids, metric_key, since,
            alignment_bit=alignment_bit,
        )

        agg_mode = "delta" if delta else "total"

        items: list[dict[str, Any]] = []
        metric_def = None
        for mid in media_item_ids:
            item = await media_repo.get(self.session, mid)
            if item is None:
                continue
            snaps = snapshots_by_id.get(mid, [])

            if aggregation and snaps:
                aggregated = _aggregate_snapshots(snaps, aggregation, agg_mode)
                raw_points = [
                    {"x": p["fetched_at"], "y": p["value"]}
                    for p in aggregated
                ]
            else:
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
                    raw_points = raw_points[1:]
                elif delta:
                    raw_points = []

            items.append({
                "media_item_id": mid,
                "media_type": item.media_type,
                "title": item.title,
                "name": item.name,
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
        aggregation: str | None = None,  # not used — release-aligned x-axis is day-offset
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
                    points = points[1:]
                elif delta:
                    points = []

                items.append({
                    "media_item_id": mid,
                    "media_type": item.media_type,
                    "title": item.title,
                    "name": item.name,
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

    async def refresh_all(self, guild_id: int, media_type: str | None = None) -> RefreshResult:
        """Refresh metrics for all media items, optionally scoped to one provider type."""
        result = RefreshResult()
        for provider in self.registry.enabled():
            if media_type is not None and provider.media_type != media_type:
                continue
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
                        self.session, item.id, metric_key, value, now,
                        alignment_mask=_compute_alignment_mask(now),
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
        mask = _compute_alignment_mask(now)
        for metric_key, value in mr.values.items():
            await media_repo.upsert_metric_cache(
                self.session, item.id, metric_key, value, now
            )
            await media_repo.insert_metric_snapshot(
                self.session, item.id, metric_key, value, now,
                alignment_mask=mask,
            )

        item.metrics_last_fetched_at = now
        return mr

    async def backfill_alignment_masks(self) -> int:
        """Compute and set alignment_mask on all snapshots where it is NULL.

        Returns the number of rows updated.
        """
        from sqlalchemy import case, update

        stmt = (
            select(MetricSnapshot.id, MetricSnapshot.fetched_at)
            .where(MetricSnapshot.alignment_mask.is_(None))
        )
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return 0

        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            case_expr = case(
                {row_id: _compute_alignment_mask(fetched_at) for row_id, fetched_at in batch},
                value=MetricSnapshot.id,
            )
            await self.session.execute(
                update(MetricSnapshot)
                .where(MetricSnapshot.id.in_([r[0] for r in batch]))
                .values(alignment_mask=case_expr)
            )
        return len(rows)

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
