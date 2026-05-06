"""Media provider registry — holds all configured providers."""

from __future__ import annotations

from .base import MediaProvider, ProviderDef


class MediaProviderRegistry:
    """Registers providers and exposes only the configured ones.

    Instantiated once at app startup and stored on ``app.state.media_registry``.
    """

    def __init__(self) -> None:
        self._providers: dict[str, MediaProvider] = {}

    def register(self, provider: MediaProvider) -> None:
        t = provider.media_type
        if t in self._providers:
            raise ValueError(f"Duplicate media type registered: {t}")
        self._providers[t] = provider

    def get(self, media_type: str) -> MediaProvider | None:
        return self._providers.get(media_type)

    def enabled(self) -> list[MediaProvider]:
        return [p for p in self._providers.values() if p.is_configured()]

    def all_defs(self) -> list[ProviderDef]:
        return [p.to_def() for p in self.enabled()]

    async def close(self) -> None:
        for provider in self._providers.values():
            await provider.close()
