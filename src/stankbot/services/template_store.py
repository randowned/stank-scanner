"""File-based template store under /data/templates.

Templates are stored as JSON files at ``data/templates/{key}.json``.
On first read, missing files are seeded from ``ALL_DEFAULTS``.
This means templates can be edited on disk and reloaded without DB changes.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from stankbot.services.default_templates import ALL_DEFAULTS

log = logging.getLogger(__name__)

_TEMPLATES_ROOT = Path(os.getenv("TEMPLATES_DIR", "./data/templates"))

_VALID_TOP_KEYS = frozenset({
    "color",
    "title",
    "description",
    "thumbnail",
    "image",
    "author",
    "footer",
    "timestamp",
    "fields",
})


def _ensure_root() -> Path:
    root = _TEMPLATES_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _template_path(key: str) -> Path:
    return _ensure_root() / f"{key}.json"


def load(key: str) -> dict[str, Any]:
    """Load a template by key. Seeds from ALL_DEFAULTS if not on disk."""
    path = _template_path(key)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)  # type: ignore[return-value]
        except Exception as exc:
            log.warning("failed to load template %r: %s; using default", key, exc)
    default = ALL_DEFAULTS.get(key)
    if default is None:
        return {}
    return dict(default)


def save(key: str, data: dict[str, Any]) -> None:
    """Write a template to disk."""
    with open(_template_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def list_templates() -> list[str]:
    """All template keys stored on disk."""
    _ensure_root()
    return [p.stem for p in _TEMPLATES_ROOT.glob("*.json")]


def seed_all() -> None:
    """Write ALL_DEFAULTS to disk if not already present."""
    _ensure_root()
    for key, data in ALL_DEFAULTS.items():
        path = _template_path(key)
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dict(data), f, indent=2, ensure_ascii=False)
            log.info("seeded template %r", key)


def remove(key: str) -> bool:
    """Delete a template from disk. Returns True if it existed."""
    path = _template_path(key)
    if path.exists():
        path.unlink()
        return True
    return False


def validate(data: dict[str, Any]) -> list[str]:
    """Return list of unknown top-level keys in template data."""
    unknown: list[str] = []
    for key in data:
        if key not in _VALID_TOP_KEYS:
            unknown.append(key)
    return unknown