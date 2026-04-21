"""Time helpers used by scheduling + rendering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def humanize_duration(seconds: float) -> str:
    """Format ``seconds`` as a compact duration string like ``2h 14m`` or
    ``45s``. Negative / zero values render as ``0s``.
    """
    s = int(max(0, seconds))
    if s == 0:
        return "0s"
    parts: list[str] = []
    days, rem = divmod(s, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    # Suppress seconds once hours/days are present — they're noise at that scale.
    if secs and not (days or hours):
        parts.append(f"{secs}s")
    return " ".join(parts) or "0s"


def next_reset_at(
    reset_hours_utc: list[int], *, now: datetime | None = None
) -> datetime:
    """Return the next scheduled reset timestamp given a sorted list of
    UTC hours (e.g. ``[7, 15, 23]``). Rolls to tomorrow if all of today's
    hours are in the past.
    """
    if not reset_hours_utc:
        raise ValueError("reset_hours_utc must not be empty")
    now = (now or datetime.now(tz=UTC)).astimezone(UTC)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for hour in sorted(reset_hours_utc):
        candidate = today_midnight + timedelta(hours=hour)
        if candidate > now:
            return candidate
    return today_midnight + timedelta(days=1, hours=min(reset_hours_utc))
