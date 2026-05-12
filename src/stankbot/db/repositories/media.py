"""Media repository — CRUD for media_items, metric_cache, and metric_snapshots."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import (
    MediaItem,
    MediaMilestone,
    MediaOwner,
    MediaOwnerMilestone,
    MediaOwnerSnapshot,
    MetricCache,
    MetricSnapshot,
)


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
    name: str | None = None,
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
        name=name,
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
    alignment_mask: int | None = None,
) -> MetricSnapshot:
    snap = MetricSnapshot(
        media_item_id=media_item_id,
        metric_key=metric_key,
        value=value,
    )
    if fetched_at is not None:
        snap.fetched_at = fetched_at
    if alignment_mask is not None:
        snap.alignment_mask = alignment_mask
    session.add(snap)
    await session.flush()
    return snap


async def get_metric_snapshots(
    session: AsyncSession,
    media_item_id: int,
    metric_key: str,
    since: datetime | None = None,
    alignment_bit: int | None = None,
) -> list[MetricSnapshot]:
    stmt = select(MetricSnapshot).where(
        MetricSnapshot.media_item_id == media_item_id,
        MetricSnapshot.metric_key == metric_key,
    )
    if since is not None:
        stmt = stmt.where(MetricSnapshot.fetched_at >= since)
    if alignment_bit is not None:
        from sqlalchemy import or_
        stmt = stmt.where(or_(
            MetricSnapshot.alignment_mask.op('&')(alignment_bit) != 0,
            MetricSnapshot.alignment_mask.is_(None),
        ))
    stmt = stmt.order_by(MetricSnapshot.fetched_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_comparison_snapshots(
    session: AsyncSession,
    media_item_ids: list[int],
    metric_key: str,
    since: datetime | None = None,
    alignment_bit: int | None = None,
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
    if alignment_bit is not None:
        from sqlalchemy import or_
        stmt = stmt.where(or_(
            MetricSnapshot.alignment_mask.op('&')(alignment_bit) != 0,
            MetricSnapshot.alignment_mask.is_(None),
        ))
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
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        ts = fetched_at.isoformat()
        if ts not in by_time:
            by_time[ts] = {}
            order.append(ts)
        by_time[ts][metric_key] = value

    return [
        {"fetched_at": ts, **metrics}
        for ts, metrics in [(t, by_time[t]) for t in order[:limit]]
    ]


# ---------------------------------------------------------------------------
# Milestones (announcement tracking)
# ---------------------------------------------------------------------------


async def insert_milestone(
    session: AsyncSession,
    media_item_id: int,
    metric_key: str,
    milestone_value: int,
) -> MediaMilestone | None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

    now = datetime.now(UTC)
    stmt = sqlite_upsert(MediaMilestone).values(
        media_item_id=media_item_id,
        metric_key=metric_key,
        milestone_value=milestone_value,
        announced_at=now,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["media_item_id", "metric_key", "milestone_value"]
    )
    result = await session.execute(stmt)
    await session.flush()
    if result.rowcount and result.rowcount > 0:  # type: ignore[attr-defined]
        row = await session.get(MediaMilestone, result.lastrowid)  # type: ignore[attr-defined]
        return row
    return None


async def has_milestone(
    session: AsyncSession,
    media_item_id: int,
    metric_key: str,
    milestone_value: int,
) -> bool:
    stmt = select(MediaMilestone).where(
        MediaMilestone.media_item_id == media_item_id,
        MediaMilestone.metric_key == metric_key,
        MediaMilestone.milestone_value == milestone_value,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Media owners (channels / artists)
# ---------------------------------------------------------------------------


async def upsert_owner(
    session: AsyncSession,
    *,
    media_type: str,
    external_id: str,
    name: str,
    external_url: str,
    thumbnail_url: str | None = None,
) -> MediaOwner:
    stmt = select(MediaOwner).where(
        MediaOwner.media_type == media_type,
        MediaOwner.external_id == external_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = MediaOwner(
            media_type=media_type,
            external_id=external_id,
            name=name,
            external_url=external_url,
            thumbnail_url=thumbnail_url,
        )
        session.add(row)
    else:
        row.name = name
        row.external_url = external_url
        if thumbnail_url is not None:
            row.thumbnail_url = thumbnail_url
        row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def get_owner(
    session: AsyncSession,
    media_type: str,
    external_id: str,
) -> MediaOwner | None:
    stmt = select(MediaOwner).where(
        MediaOwner.media_type == media_type,
        MediaOwner.external_id == external_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_owner_by_id(
    session: AsyncSession,
    owner_id: int,
) -> MediaOwner | None:
    return await session.get(MediaOwner, owner_id)


async def insert_owner_snapshot(
    session: AsyncSession,
    media_owner_id: int,
    metric_key: str,
    value: int,
    fetched_at: datetime | None = None,
) -> MediaOwnerSnapshot:
    snap = MediaOwnerSnapshot(
        media_owner_id=media_owner_id,
        metric_key=metric_key,
        value=value,
    )
    if fetched_at is not None:
        snap.fetched_at = fetched_at
    session.add(snap)
    await session.flush()
    return snap


async def get_owner_latest_metrics(
    session: AsyncSession,
    media_owner_id: int,
) -> dict[str, dict[str, int | str]]:
    """Return {metric_key: {value, fetched_at}} for the latest snapshot
    of each metric for an owner."""
    from sqlalchemy import func

    subq = (
        select(
            MediaOwnerSnapshot.metric_key,
            func.max(MediaOwnerSnapshot.id).label("max_id"),
        )
        .where(MediaOwnerSnapshot.media_owner_id == media_owner_id)
        .group_by(MediaOwnerSnapshot.metric_key)
        .subquery()
    )
    stmt = (
        select(MediaOwnerSnapshot)
        .where(
            MediaOwnerSnapshot.media_owner_id == media_owner_id,
            MediaOwnerSnapshot.id.in_(select(subq.c.max_id)),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        r.metric_key: {
            "value": r.value,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else "",
        }
        for r in rows
    }


async def get_owner_snapshots_pivoted(
    session: AsyncSession,
    media_owner_id: int,
    limit: int = 20,
) -> list[dict[str, int | str]]:
    """Return last N owner snapshots pivoted: one row per timestamp, all metrics as columns."""
    subq = (
        select(
            MediaOwnerSnapshot.fetched_at,
            MediaOwnerSnapshot.metric_key,
            MediaOwnerSnapshot.value,
        )
        .where(MediaOwnerSnapshot.media_owner_id == media_owner_id)
        .order_by(MediaOwnerSnapshot.fetched_at.desc())
        .limit(limit * 5)
        .subquery()
    )
    stmt = (
        select(subq.c.fetched_at, subq.c.metric_key, subq.c.value)
        .order_by(subq.c.fetched_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    by_time: dict[str, dict[str, int]] = {}
    order: list[str] = []
    for fetched_at, metric_key, value in rows:
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        ts = fetched_at.isoformat()
        if ts not in by_time:
            by_time[ts] = {}
            order.append(ts)
        by_time[ts][metric_key] = value

    return [
        {"fetched_at": ts, **metrics}
        for ts, metrics in [(t, by_time[t]) for t in order[:limit]]
    ]


async def get_owners_for_guild(
    session: AsyncSession,
    guild_id: int,
    media_type: str | None = None,
) -> list[dict[str, object]]:
    """Return owners that have media items in a guild, with latest metrics
    and media item summaries."""
    from sqlalchemy import and_

    join_conds = and_(
        MediaItem.channel_id == MediaOwner.external_id,
        MediaItem.media_type == MediaOwner.media_type,
    )
    stmt = (
        select(MediaOwner, MediaItem)
        .join(MediaItem, join_conds)
        .where(MediaItem.guild_id == guild_id)
    )
    if media_type is not None:
        stmt = stmt.where(MediaOwner.media_type == media_type)
    stmt = stmt.order_by(MediaOwner.name.asc())
    rows = (await session.execute(stmt)).all()

    owner_map: dict[int, dict[str, object]] = {}
    for owner, item in rows:
        if owner.id not in owner_map:
            owner_map[owner.id] = {
                "id": owner.id,
                "media_type": owner.media_type,
                "external_id": owner.external_id,
                "name": owner.name,
                "external_url": owner.external_url,
                "thumbnail_url": owner.thumbnail_url,
                "media_items": [],
            }
        owner_map[owner.id]["media_items"].append({  # type: ignore[index]
            "id": item.id,
            "title": item.title,
            "name": item.name,
            "external_id": item.external_id,
        })

    for owner_id, summary in owner_map.items():
        metrics = await get_owner_latest_metrics(session, owner_id)
        latest_ts = ""
        for m in metrics.values():
            if isinstance(m, dict):
                mt = m.get("fetched_at", "")
                if mt and mt > latest_ts:
                    latest_ts = str(mt)
        summary["metrics"] = metrics  # type: ignore[index]
        summary["fetched_at"] = latest_ts  # type: ignore[index]

    return list(owner_map.values())


# ---------------------------------------------------------------------------
# Owner milestones (announcement tracking)
# ---------------------------------------------------------------------------


async def insert_owner_milestone(
    session: AsyncSession,
    media_owner_id: int,
    metric_key: str,
    milestone_value: int,
) -> MediaOwnerMilestone | None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

    now = datetime.now(UTC)
    stmt = sqlite_upsert(MediaOwnerMilestone).values(
        media_owner_id=media_owner_id,
        metric_key=metric_key,
        milestone_value=milestone_value,
        announced_at=now,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["media_owner_id", "metric_key", "milestone_value"]
    )
    result = await session.execute(stmt)
    await session.flush()
    if result.rowcount and result.rowcount > 0:  # type: ignore[attr-defined]
        row = await session.get(MediaOwnerMilestone, result.lastrowid)  # type: ignore[attr-defined]
        return row
    return None


async def has_owner_milestone(
    session: AsyncSession,
    media_owner_id: int,
    metric_key: str,
    milestone_value: int,
) -> bool:
    stmt = select(MediaOwnerMilestone).where(
        MediaOwnerMilestone.media_owner_id == media_owner_id,
        MediaOwnerMilestone.metric_key == metric_key,
        MediaOwnerMilestone.milestone_value == milestone_value,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
