"""Media provider exports."""

from .base import MediaProvider, MetricDef, MetricResult, ProviderDef, ResolvedMedia
from .registry import MediaProviderRegistry
from .spotify import SpotifyProvider
from .youtube import YouTubeProvider

__all__ = [
    "MediaProvider",
    "MediaProviderRegistry",
    "MetricDef",
    "MetricResult",
    "ProviderDef",
    "ResolvedMedia",
    "YouTubeProvider",
    "SpotifyProvider",
]
