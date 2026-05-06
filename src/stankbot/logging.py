from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import UTC, datetime

# In-memory ring buffer feeding ``/stank-admin log``. Populated by the
# handler installed in ``configure_logging`` below.
_LOG_RING: deque[str] = deque(maxlen=500)


def tail_log(lines: int = 50) -> list[str]:
    """Return the most recent ``lines`` formatted log messages."""
    if lines <= 0:
        return []
    buf = list(_LOG_RING)
    return buf[-lines:]


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _LOG_RING.append(self.format(record))
        except Exception:  # pragma: no cover - never let logging crash
            self.handleError(record)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)

    # Railway already tags every stdout line with a timestamp and a
    # severity badge in its UI, so we drop both ``%(asctime)s`` and
    # ``%(levelname)s`` from the stream format to avoid visible
    # duplicates. The ring buffer (fed to ``/stank-admin log``) keeps
    # both since it's read out-of-band with no surrounding metadata.
    stream_fmt = logging.Formatter("%(name)s: %(message)s")
    ring_fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter() if fmt == "json" else stream_fmt)
    root.addHandler(handler)

    ring = _RingHandler()
    ring.setFormatter(ring_fmt)
    root.addHandler(ring)

    # Quiet noisy libs
    logging.getLogger("discord.gateway").setLevel("WARNING")
    logging.getLogger("discord.client").setLevel("WARNING")
    logging.getLogger("apscheduler.scheduler").setLevel("WARNING")
    # httpx logs full request URLs at INFO which leaks API keys
    # (YouTube, Spotify) into Railway logs. Suppress them.
    logging.getLogger("httpx").setLevel("WARNING")
    # Uvicorn's default config disables propagation and installs its own
    # handlers; with ``log_config=None`` we want the opposite — no child
    # handlers, just propagate to root. Also mute its access log as a
    # safety net in case ``access_log=False`` is forgotten.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # Rewrite ``uvicorn.error`` → ``uvicorn`` so startup messages
    # don't misleadingly show ``uvicorn.error:``.
    class _RenameFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if record.name == "uvicorn.error":
                record.name = "uvicorn"
            return True
    logging.getLogger("uvicorn.error").addFilter(_RenameFilter())
    logging.getLogger("uvicorn.access").setLevel("WARNING")
