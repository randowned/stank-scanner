"""Chart image renderer for media metric time-series.

Uses Pillow to generate PNG chart images (public chart endpoint,
Discord embed). Designed to match the frontend Chart.js dark theme
so images look consistent in Discord embeds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from stankbot.db.models import MetricSnapshot

# ---------------------------------------------------------------------------
# Font loading — try system TTF, fall back to default bitmap
# ---------------------------------------------------------------------------

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",            # Alpine
    "C:/Windows/Fonts/arial.ttf",                        # Windows
    "/System/Library/Fonts/Helvetica.ttc",               # macOS
]

def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


_FONT_TITLE = _load_font(36)
_FONT_LABEL = _load_font(18)
_FONT_TICK = _load_font(14)

# Pre-compute average char widths for text measurement
_FONT_LABEL_AVG_W = _FONT_LABEL.getlength("0") if hasattr(_FONT_LABEL, "getlength") else 8
_FONT_TICK_AVG_W = _FONT_TICK.getlength("0") if hasattr(_FONT_TICK, "getlength") else 6

# ---------------------------------------------------------------------------
# Layout constants (16:9 canvas)
# ---------------------------------------------------------------------------

WIDTH = 1200
HEIGHT = 675
PAD_LEFT = 110
PAD_RIGHT = 30
PAD_TOP = 60
PAD_BOTTOM = 80

CHART_LEFT = PAD_LEFT
CHART_RIGHT = WIDTH - PAD_RIGHT
CHART_TOP = PAD_TOP
CHART_BOTTOM = HEIGHT - PAD_BOTTOM
CHART_W = CHART_RIGHT - CHART_LEFT
CHART_H = CHART_BOTTOM - CHART_TOP

# Theme colours
BG = "#1a1d24"
GRID = "#262a33"
AXIS = "#9aa4b2"
LINE = "#3b82f6"
TITLE_COLOR = "#e2e8f0"
LABEL_COLOR = "#9aa4b2"


def _format_number(n: int | float) -> str:
    """Human-readable metric value."""
    n = float(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    if n == int(n):
        return str(int(n))
    return f"{n:.1f}"


def _nice_range(vmin: int | float, vmax: int | float) -> tuple[int | float, int | float, int]:
    """Compute nice y-axis min/max and number of grid lines."""
    span = vmax - vmin
    if span == 0:
        return vmin - 1, vmax + 1, 5
    # Aim for ~5 horizontal grid lines
    raw_step = span / 5
    # Round step to nice magnitude
    magnitude = 10 ** (len(str(int(raw_step))) - 1) if raw_step >= 1 else 0.1
    if raw_step >= 1:
        nice = int(raw_step / magnitude) * magnitude
        if nice == 0:
            nice = magnitude
    else:
        nice = raw_step
    nice_floor = int((vmin - nice * 0.1) / nice) * nice
    nice_ceil = int((vmax + nice * 0.1) / nice + 1) * nice
    grid_lines = int((nice_ceil - nice_floor) / nice)
    if grid_lines < 3:
        nice = nice / 2
        nice_floor = int((vmin - nice * 0.1) / nice) * nice
        nice_ceil = int((vmax + nice * 0.1) / nice + 1) * nice
        grid_lines = int((nice_ceil - nice_floor) / nice)
    return nice_floor, nice_ceil, grid_lines


def render_media_chart(
    *,
    snapshots: list[MetricSnapshot],
    title: str,
    metric_label: str,
    duration_hours: float,
    mode: str = "total",
    width: int = WIDTH,
    height: int = HEIGHT,
) -> bytes:
    """Render a single-line time-series chart as PNG bytes."""
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # ------------------------------------------------------------------
    # Data mapping
    # ------------------------------------------------------------------
    raw_values = [s.value for s in snapshots]
    if mode == "delta" and len(raw_values) >= 2:
        values = [raw_values[i] - raw_values[i - 1] for i in range(1, len(raw_values))]
        snapshots = snapshots[1:]
    elif mode == "delta":
        values = []
        snapshots = []
    else:
        values = raw_values

    if not snapshots:
        draw.text((width / 2 - 80, height / 2), "No data available", fill=LABEL_COLOR, font=_FONT_LABEL)
        return _save_bytes(img)
    times = [(s.fetched_at.astimezone(UTC) if isinstance(s.fetched_at, datetime) else s.fetched_at) for s in snapshots]
    times_dt = [t if isinstance(t, datetime) else datetime.fromisoformat(str(t).replace("Z", "+00:00")) for t in times]

    vmin = min(values)
    vmax = max(values)
    y_floor, y_ceil, num_grid = _nice_range(vmin, vmax)
    y_span = y_ceil - y_floor

    tmin = min(times_dt)
    tmax = max(times_dt)
    t_span = (tmax - tmin).total_seconds()
    if t_span == 0:
        t_span = 60  # 1 minute minimum to avoid division by zero

    # ------------------------------------------------------------------
    # Helper: map data coordinates → pixel coordinates
    # ------------------------------------------------------------------
    def px_x(dt: datetime) -> float:
        frac = (dt - tmin).total_seconds() / t_span
        return CHART_LEFT + frac * CHART_W

    def px_y(val: int) -> float:
        return CHART_BOTTOM - float(val - y_floor) / y_span * CHART_H

    # ------------------------------------------------------------------
    # Horizontal grid lines + Y labels
    # ------------------------------------------------------------------
    step = y_span / num_grid if num_grid > 0 else y_span
    for i in range(num_grid + 1):
        val = y_floor + i * step
        y = px_y(int(val))
        draw.line([(CHART_LEFT, y), (CHART_RIGHT, y)], fill=GRID, width=1)
        label = _format_number(val)
        tw = _FONT_LABEL_AVG_W * len(label)
        draw.text((CHART_LEFT - tw - 8, y - _FONT_LABEL_AVG_W * 0.6), label, fill=LABEL_COLOR, font=_FONT_LABEL)

    # ------------------------------------------------------------------
    # Vertical day-boundary lines + X labels
    # ------------------------------------------------------------------
    show_date = (t_span >= 86400)  # multi-day: show date

    if show_date:
        # Draw midnight vertical lines for each day in range
        from datetime import timedelta as td
        day = datetime(tmin.year, tmin.month, tmin.day, tzinfo=tmin.tzinfo)
        while day <= tmax:
            cx = px_x(day)
            if CHART_LEFT <= cx <= CHART_RIGHT:
                draw.line([(int(cx), CHART_TOP), (int(cx), CHART_BOTTOM)], fill=GRID, width=1)
                lbl = day.strftime("%b %d")
                tw = _FONT_TICK_AVG_W * len(lbl)
                draw.text((int(cx) - tw // 2, CHART_BOTTOM + 4), lbl, fill=LABEL_COLOR, font=_FONT_TICK)
            day += td(days=1)

    # Smaller hour ticks when spanning a day or less
    if t_span <= 86400 * 2:
        from datetime import timedelta as td
        tick_dt = tmin.replace(minute=0, second=0, microsecond=0)
        while tick_dt <= tmax:
            cx = px_x(tick_dt)
            if CHART_LEFT <= cx <= CHART_RIGHT:
                lbl = tick_dt.strftime("%b %d %H:%M" if show_date else "%H:%M")
                tw = _FONT_TICK_AVG_W * len(lbl)
                draw.text((int(cx) - tw // 2, CHART_BOTTOM + 18), lbl, fill=LABEL_COLOR, font=_FONT_TICK)
            tick_dt += td(hours=2) if t_span > 43200 else td(hours=1)

    # ------------------------------------------------------------------
    # Data line
    # ------------------------------------------------------------------
    if len(snapshots) >= 2:
        pts = [(px_x(dt), px_y(snap.value)) for snap, dt in zip(snapshots, times_dt, strict=True)]
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=LINE, width=2)

    # ------------------------------------------------------------------
    # Data dots
    # ------------------------------------------------------------------
    for _i, (snap, dt) in enumerate(zip(snapshots, times_dt, strict=True)):
        cx = px_x(dt)
        cy = px_y(snap.value)
        r = 3
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LINE)

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------
    draw.text((PAD_LEFT, 12), title, fill=TITLE_COLOR, font=_FONT_TITLE)

    # Y-axis label
    draw.text((4, CHART_TOP + CHART_H // 2 - 8), metric_label, fill=LABEL_COLOR, font=_FONT_LABEL)

    return _save_bytes(img)


def _save_bytes(img: Image.Image) -> bytes:
    """Encode image to PNG bytes in memory."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
