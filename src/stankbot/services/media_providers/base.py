"""Media provider abstraction — agnostic interface for any media platform."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MetricDef:
    """Describes a metric this provider can measure."""

    key: str
    label: str
    format: str = "number"  # number | percentage | duration
    icon: str = ""


@dataclass(slots=True)
class ProviderDef:
    """Lightweight provider descriptor for API serialization (no secrets)."""

    type: str
    label: str
    icon: str
    metrics: list[MetricDef]


@dataclass(slots=True)
class ResolvedMedia:
    """Result of resolving a URL/ID into structured metadata."""

    external_id: str
    title: str
    channel_name: str | None = None
    channel_id: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    extra: dict[str, str | int | None] = field(default_factory=dict)


@dataclass(slots=True)
class MetricResult:
    """Metric values for a single external_id after a fetch."""

    external_id: str
    values: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class OwnerResult:
    """Owner-level data fetched from a provider (channel/artist stats)."""

    external_id: str
    name: str
    external_url: str
    thumbnail_url: str | None = None
    metrics: dict[str, int] = field(default_factory=dict)


class MediaProvider(ABC):
    """Provider-agnostic interface for any media platform.

    Each provider handles one platform type: YouTube, Spotify, etc.
    Enabled only when its credentials are configured.
    """

    media_type: str = ""
    label: str = ""
    icon: str = ""
    metrics: list[MetricDef] = []
    owner_metrics: list[MetricDef] = []

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def resolve(self, url_or_id: str) -> ResolvedMedia | None: ...

    @abstractmethod
    async def fetch_metrics(
        self, external_ids: list[str]
    ) -> list[MetricResult]: ...

    async def can_fetch_metrics(
        self,
        session: Any,
        guild_id: int,
    ) -> bool:
        """Whether this provider can fetch metrics for a guild.

        Default: same as is_configured(). Override when metrics need
        per-guild credentials (e.g. OAuth tokens).
        """
        return self.is_configured()

    async def fetch_owner(self, external_id: str) -> OwnerResult | None:
        """Fetch owner-level metrics for a channel/artist.

        Default: not supported (returns None). Override in providers
        that have an owner concept (YouTube channels, Spotify artists).
        """
        return None

    @abstractmethod
    async def health_check(self) -> bool: ...

    async def close(self) -> None:
        """Release any resources held by this provider (HTTP clients, etc.)."""

    def to_def(self) -> ProviderDef:
        return ProviderDef(
            type=self.media_type,
            label=self.label,
            icon=self.icon,
            metrics=self.metrics,
        )
