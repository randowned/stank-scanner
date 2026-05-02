"""Media repository — CRUD for media_items, metric_cache, and metric_snapshots."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import MediaItem, MetricCache, MetricSnapshot


async def add(
    session: AsyncSession,
    *,
    guild_id: int,
    media_type: str,
    external_id: str,
    title: str,
    channel_name: str | None = None,
    channel_id: str | None = None,
    thumbnail_url: str | None = None,
    published_at: datetime | None = None,
    duration_seconds: int | None = None,
    added_by: int,
    slug: str | None = None,
) -> MediaItem:
    item = MediaItem(
        guild_id=guild_id,
        media_type=media_type,
        external_id=external_id,
        title=title,
        channel_name=channel_name,
        channel_id=channel_id,
        thumbnail_url=thumbnail_url,
        published_at=published_at,
        duration_seconds=duration_seconds,
        added_by=added_by,
        name=slug,
    )
    session.add(item)
    await session.flush()
    return item


async def get(session: AsyncSession, media_item_id: int) -> MediaItem | None:
    return await session.get(MediaItem, media_item_id)


async def list_all(
    session: AsyncSession,
    guild_id: int,
    media_type: str | None = None,
) -> list[MediaItem]:
    stmt = select(MediaItem).where(MediaItem.guild_id == guild_id)
    if media_type is not None:
        stmt = stmt.where(MediaItem.media_type == media_type)
    stmt = stmt.order_by(MediaItem.published_at.desc().nullslast(), MediaItem.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_name(
    session: AsyncSession,
    guild_id: int,
    media_type: str,
    name: str,
) -> MediaItem | None:
    stmt = select(MediaItem).where(
        MediaItem.guild_id == guild_id,
        MediaItem.media_type == media_type,
        MediaItem.name == name,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_names(
    session: AsyncSession,
    guild_id: int,
    names: list[str],
) -> dict[str, MediaItem]:
    """Bulk lookup by name; returns {name: MediaItem} for found items."""
    if not names:
        return {}
    stmt = select(MediaItem).where(
        MediaItem.guild_id == guild_id,
        MediaItem.name.in_(names),
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {r.name: r for r in rows if r.name}


async def is_name_taken(
    session: AsyncSession,
    guild_id: int,
    media_type: str,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(MediaItem).where(
        MediaItem.guild_id == guild_id,
        MediaItem.media_type == media_type,
        MediaItem.name == name,
    )
    if exclude_id is not None:
        stmt = stmt.where(MediaItem.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def is_external_id_taken(
    session: AsyncSession,
    guild_id: int,
    media_type: str,
    external_id: str,
) -> bool:
    stmt = select(MediaItem).where(
        MediaItem.guild_id == guild_id,
        MediaItem.media_type == media_type,
        MediaItem.external_id == external_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def delete_media(session: AsyncSession, media_item_id: int) -> bool:
    item = await session.get(MediaItem, media_item_id)
    if item is None:
        return False
    await session.delete(item)
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Metric cache (latest values)
# ---------------------------------------------------------------------------


async def upsert_metric_cache(
    session: AsyncSession,
    media_item_id: int,
    metric_key: str,
    value: int,
    fetched_at: datetime | None = None,
) -> None:
    row = await session.get(MetricCache, (media_item_id, metric_key))
    if row is None:
        row = MetricCache(media_item_id=media_item_id, metric_key=metric_key, value=value)
        if fetched_at is not None:
            row.fetched_at = fetched_at
        session.add(row)
    else:
        row.value = value
        if fetched_at is not None:
            row.fetched_at = fetched_at
        else:
            row.fetched_at = datetime.now(UTC)


async def get_metric_cache(
    session: AsyncSession,
    media_item_id: int,
) -> dict[str, dict[str, int | str]]:
    """Return {metric_key: {value: int, fetched_at: iso_str}} for one item."""
    stmt = select(MetricCache).where(MetricCache.media_item_id == media_item_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        r.metric_key: {
            "value": r.value,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else "",
        }
        for r in rows
    }


async def get_metrics_for_items(
    session: AsyncSession,
    media_item_ids: list[int],
) -> dict[int, dict[str, dict[str, int | str]]]:
    """Return {media_item_id: {metric_key: {value, fetched_at}}} for multiple items."""
    if not media_item_ids:
        return {}
    stmt = select(MetricCache).where(MetricCache.media_item_id.in_(media_item_ids))
    rows = (await session.execute(stmt)).scalars().all()
    result: dict[int, dict[str, dict[str, int | str]]] = {}
    for r in rows:
        result.setdefault(r.media_item_id, {})[r.metric_key] = {
            "value": r.value,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else "",
        }
    return result


# ---------------------------------------------------------------------------
# Metric snapshots (time-series)
# ---------------------------------------------------------------------------


async def insert_metric_snapshot(
    session: AsyncSession,
    media_item_id: int,
    metric_key: str,
    value: int,
    fetched_at: datetime | None = None,
) -> MetricSnapshot:
    snap = MetricSnapshot(
        media_item_id=media_item_id,
        metric_key=metric_key,
        value=value,
    )
    if fetched_at is not None:
        snap.fetched_at = fetched_at
    session.add(snap)
    await session.flush()
    return snap


async def get_metric_snapshots(
    session: AsyncSession,
    media_item_id: int,
    metric_key: str,
    since: datetime | None = None,
) -> list[MetricSnapshot]:
    stmt = select(MetricSnapshot).where(
        MetricSnapshot.media_item_id == media_item_id,
        MetricSnapshot.metric_key == metric_key,
    )
    if since is not None:
        stmt = stmt.where(MetricSnapshot.fetched_at >= since)
    stmt = stmt.order_by(MetricSnapshot.fetched_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_comparison_snapshots(
    session: AsyncSession,
    media_item_ids: list[int],
    metric_key: str,
    since: datetime | None = None,
) -> dict[int, list[MetricSnapshot]]:
    """Return {media_item_id: [snapshots]} for comparison charts."""
    if not media_item_ids:
        return {}
    stmt = select(MetricSnapshot).where(
        MetricSnapshot.media_item_id.in_(media_item_ids),
        MetricSnapshot.metric_key == metric_key,
    )
    if since is not None:
        stmt = stmt.where(MetricSnapshot.fetched_at >= since)
    stmt = stmt.order_by(MetricSnapshot.fetched_at.asc())
    rows = (await session.execute(stmt)).scalars().all()
    result: dict[int, list[MetricSnapshot]] = {}
    for r in rows:
        result.setdefault(r.media_item_id, []).append(r)
    return result


async def get_metric_snapshots_pivoted(
    session: AsyncSession,
    media_item_id: int,
    limit: int = 20,
) -> list[dict[str, int | str]]:
    """Return last N snapshots pivoted: one row per timestamp, all metrics as columns."""
    subq = (
        select(
            MetricSnapshot.fetched_at,
            MetricSnapshot.metric_key,
            MetricSnapshot.value,
        )
        .where(MetricSnapshot.media_item_id == media_item_id)
        .order_by(MetricSnapshot.fetched_at.desc())
        .limit(limit * 5)  # oversample since we'll pivot
        .subquery()
    )
    stmt = (
        select(subq.c.fetched_at, subq.c.metric_key, subq.c.value)
        .order_by(subq.c.fetched_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    # Pivot: group by fetched_at
    by_time: dict[str, dict[str, int]] = {}
    order: list[str] = []
    for fetched_at, metric_key, value in rows:
        ts = fetched_at.isoformat()
        if ts not in by_time:
            by_time[ts] = {}
            order.append(ts)
        by_time[ts][metric_key] = value

    return [
        {"fetched_at": ts, **metrics}
        for ts, metrics in [(t, by_time[t]) for t in order[:limit]]
    ]
