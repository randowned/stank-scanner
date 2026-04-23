"""Tests for the dashboard_url_for helper."""

from __future__ import annotations

import pytest

from stankbot.services.dashboard_urls import dashboard_url_for


BASE = "https://bot.example.com"


def test_board() -> None:
    assert dashboard_url_for("board", base_url=BASE) == f"{BASE}/"


def test_player() -> None:
    assert dashboard_url_for("player", base_url=BASE, user_id=42) == f"{BASE}/player/42"


def test_chain() -> None:
    assert dashboard_url_for("chain", base_url=BASE, chain_id=7) == f"{BASE}/chain/7"


def test_session() -> None:
    assert dashboard_url_for("session", base_url=BASE, session_id=3) == f"{BASE}/session/3"


def test_admin_prefix() -> None:
    assert dashboard_url_for("admin_templates", base_url=BASE) == f"{BASE}/admin/templates"


def test_trailing_slash_normalized() -> None:
    assert dashboard_url_for("board", base_url="https://x.com/") == "https://x.com/"


def test_chain_requires_id() -> None:
    with pytest.raises(ValueError):
        dashboard_url_for("chain", base_url=BASE)


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError):
        dashboard_url_for("nope", base_url=BASE)  # type: ignore[arg-type]
