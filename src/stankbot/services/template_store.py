"""Per-guild template store backed by the ``guild_settings`` table.

Templates are stored as JSON rows in ``guild_settings`` keyed by
``(guild_id, template_key)``.  When a guild has no override for a given
key the built-in default from ``ALL_DEFAULTS`` is returned instead.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.services.default_templates import ALL_DEFAULTS

log = logging.getLogger(__name__)

_VALID_TOP_KEYS = frozenset({
    "color",
    "title",
    "url",
    "description",
    "thumbnail",
    "image",
    "author",
    "footer",
    "timestamp",
    "fields",
})


async def load(key: str, session: AsyncSession, guild_id: int) -> dict[str, Any]:
    """Load a guild template, falling back to the built-in default."""
    from stankbot.services.settings_service import SettingsService

    guild_data = await SettingsService(session).get(guild_id, key)
    if guild_data is not None:
        return guild_data
    default = ALL_DEFAULTS.get(key)
    if default is None:
        return {}
    return dict(default)


def load_default(key: str) -> dict[str, Any]:
    """Return the built-in default template (no DB access)."""
    default = ALL_DEFAULTS.get(key)
    if default is None:
        return {}
    return dict(default)


async def save(key: str, data: dict[str, Any], session: AsyncSession, guild_id: int) -> None:
    """Write a guild template to the database."""
    from stankbot.services.settings_service import SettingsService

    await SettingsService(session).set(guild_id, key, data)


def all_keys() -> list[str]:
    """All known template keys (from built-in defaults)."""
    return sorted(ALL_DEFAULTS.keys())


def validate(data: dict[str, Any]) -> list[str]:
    """Return list of unknown top-level keys in template data."""
    unknown: list[str] = []
    for key in data:
        if key not in _VALID_TOP_KEYS:
            unknown.append(key)
    return unknown
