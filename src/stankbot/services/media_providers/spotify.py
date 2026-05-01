"""Spotify provider — Spotify Web API integration (client credentials)."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

import httpx

from .base import MediaProvider, MetricDef, MetricResult, ResolvedMedia

log = logging.getLogger(__name__)

_SPOTIFY_URI_RE = re.compile(r"spotify:(track|album):(\w+)", re.IGNORECASE)
_SPOTIFY_URL_RE = re.compile(
    r"(?:https?://)?open\.spotify\.com/(track|album)/(\w+)", re.IGNORECASE
)

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"


class SpotifyProvider(MediaProvider):
    media_type = "spotify"
    label = "Spotify"
    icon = "🟢"
    metrics = [
        MetricDef("popularity", "Popularity", "percentage", "🔥"),
    ]

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_token(self) -> str | None:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        if not self._client_id or not self._client_secret:
            return None

        client = self._get_client()
        try:
            resp = await client.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                timeout=10.0,
            )
            if resp.status_code != 200:
                try:
                    body = resp.text
                except Exception:
                    body = "<unreadable>"
                log.warning("Spotify token request failed: %d — %s", resp.status_code, body[:200])
                return None
            data: dict[str, Any] = resp.json()
            self._token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in
            return self._token
        except httpx.HTTPError as exc:
            log.warning("Spotify token request error: %s", exc)
            return None

    @staticmethod
    def extract_id(url_or_uri: str) -> tuple[str, str] | None:
        """Return (type, id) or None.  type is 'track' or 'album'."""
        m = _SPOTIFY_URI_RE.search(url_or_uri)
        if m:
            return m.group(1).lower(), m.group(2)
        m = _SPOTIFY_URL_RE.search(url_or_uri)
        if m:
            return m.group(1).lower(), m.group(2)
        return None

    async def resolve(self, url_or_uri: str) -> ResolvedMedia | None:
        extracted = self.extract_id(url_or_uri)
        if not extracted:
            return None
        kind, spotify_id = extracted
        token = await self._ensure_token()
        if not token:
            return None

        client = self._get_client()
        url = f"{_API_BASE}/{kind}s/{spotify_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 401:
                self._token = None  # force re-auth
                return None
            if resp.status_code != 200:
                return None
            data: dict[str, Any] = resp.json()

            name = data.get("name", "")
            duration_ms = data.get("duration_ms")
            duration_seconds = duration_ms // 1000 if duration_ms else None

            artists = data.get("artists", [])
            artist_name = artists[0].get("name") if artists else None

            album = data.get("album", {})
            channel_name = artist_name
            if album:
                album_name = album.get("name")
                if album_name and artist_name:
                    channel_name = f"{artist_name} — {album_name}"

            images = data.get("images") or (album.get("images") if album else None)
            thumbnail = images[0].get("url") if images else None

            pub_str = data.get("release_date") or album.get("release_date")
            pub = None
            if pub_str:
                try:
                    pub = datetime.fromisoformat(pub_str)
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=__import__("datetime").timezone.utc)
                except ValueError:
                    pass

            return ResolvedMedia(
                external_id=spotify_id,
                title=name,
                channel_name=channel_name,
                channel_id=artists[0].get("id") if artists else None,
                thumbnail_url=thumbnail,
                published_at=pub,
                duration_seconds=duration_seconds,
                extra={"spotify_type": kind},
            )
        except httpx.HTTPError:
            return None

    async def fetch_metrics(self, external_ids: list[str]) -> list[MetricResult]:
        token = await self._ensure_token()
        if not token:
            return [MetricResult(external_id=eid, error="auth_failed") for eid in external_ids]

        results: list[MetricResult] = []
        client = self._get_client()
        headers = {"Authorization": f"Bearer {token}"}

        for spotify_id in external_ids:
            try:
                url = f"{_API_BASE}/tracks/{spotify_id}"
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code == 401:
                    self._token = None
                    results.append(MetricResult(external_id=spotify_id, error="auth_failed"))
                    continue
                if resp.status_code == 404:
                    results.append(MetricResult(external_id=spotify_id, error="not_found"))
                    continue
                if resp.status_code != 200:
                    results.append(MetricResult(external_id=spotify_id, error="api_error"))
                    continue

                data: dict[str, Any] = resp.json()
                popularity = data.get("popularity", 0)
                results.append(
                    MetricResult(
                        external_id=spotify_id,
                        values={"popularity": popularity},
                    )
                )
            except httpx.HTTPError:
                results.append(MetricResult(external_id=spotify_id, error="timeout"))

        return results

    async def health_check(self) -> bool:
        token = await self._ensure_token()
        return token is not None
