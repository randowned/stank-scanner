"""Dashboard URL resolver shared by bot embeds and web redirects.

Builds absolute URLs to dashboard pages. Pure function — no FastAPI /
discord.py imports, safe to call from cogs, services, and template
rendering alike.
"""

from __future__ import annotations

from typing import Literal

Kind = Literal[
    "board",
    "player",
    "chain",
    "session",
    "admin",
    "admin_settings",
    "admin_altar",
    "admin_roles",
    "admin_audit",
    "admin_announcements",
    "admin_maintenance",
    "admin_config",
    "admin_templates",
]


def dashboard_url_for(
    kind: Kind,
    *,
    base_url: str,
    user_id: int | None = None,
    chain_id: int | None = None,
    session_id: int | None = None,
) -> str:
    """Build an absolute URL to a dashboard page.

    ``base_url`` is the origin (e.g. ``https://bot.example.com``).
    """
    base = base_url.rstrip("/")

    if kind == "board":
        return f"{base}/"
    if kind == "player":
        if user_id is None:
            raise ValueError("player URL requires user_id")
        return f"{base}/player/{user_id}"
    if kind == "chain":
        if chain_id is None:
            raise ValueError("chain URL requires chain_id")
        return f"{base}/chain/{chain_id}"
    if kind == "session":
        if session_id is None:
            raise ValueError("session URL requires session_id")
        return f"{base}/session/{session_id}"
    if kind == "admin":
        return f"{base}/admin"
    if kind == "admin_settings":
        return f"{base}/admin/settings"
    if kind == "admin_altar":
        return f"{base}/admin/altar"
    if kind == "admin_roles":
        return f"{base}/admin/roles"
    if kind == "admin_audit":
        return f"{base}/admin/audit"
    if kind == "admin_announcements":
        return f"{base}/admin/announcements"
    if kind == "admin_maintenance":
        return f"{base}/admin/maintenance"
    if kind == "admin_config":
        return f"{base}/admin/config"
    if kind == "admin_templates":
        return f"{base}/admin/templates"

    raise ValueError(f"unknown dashboard URL kind: {kind!r}")
