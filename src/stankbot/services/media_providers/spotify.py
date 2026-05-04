"""Spotify provider — public API for resolve, Partner API for playcount metrics."""

from __future__ import annotations

import asyncio
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
_PARTNER_BASE = "https://api-partner.spotify.com/pathfinder/v2/query"
_PARTNER_TOKEN_URL = "https://open.spotify.com/get_access_token"

# Persisted query hash for queryArtistOverview (extracted from web player JS)
_ARTIST_OVERVIEW_SHA256 = "7f86ff63e38c24973a2842b672abe44c910c1973978dc8a4a0cb648edef34527"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

_CLIENT_TOKEN_RE = re.compile(r'(?:clientToken|client_token|client-token)\s*[=:]\s*"([A-Za-z0-9+/=]{100,})"')
_APP_VERSION_RE = re.compile(r'"appVersion"\s*:\s*"(\d+)"')


class SpotifyProvider(MediaProvider):
    media_type = "spotify"
    label = "Spotify"
    icon = "\U0001f7e2"
    metrics = [
        MetricDef("playcount", "Play Count", "number", "\U0001f3a7"),
    ]

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        client_token: str | None = None,
        sp_dc: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        # Pre-set client-token from env var (avoids scraping Spotify's web player)
        self._client_token: str | None = client_token
        # sp_dc cookie for Partner API token exchange (can be overridden at runtime)
        self._sp_dc: str | None = sp_dc
        self._public_client: httpx.AsyncClient | None = None
        self._partner_client: httpx.AsyncClient | None = None
        # Public API token (client credentials — for resolve only)
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        # Partner API token (from sp_dc cookie exchange)
        self._partner_token: str | None = None
        self._partner_token_expires_at: float = 0.0
        self._app_version: str = "896000000"
        self._client_token_lock = asyncio.Lock()
        # Session context injected by MediaService before fetch_metrics
        self._session: Any | None = None
        self._session_guild_id: int | None = None

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def set_session_context(self, session: Any, guild_id: int) -> None:
        """Store DB session context for use by fetch_metrics."""
        self._session = session
        self._session_guild_id = guild_id

    def set_sp_dc(self, sp_dc: str) -> None:
        self._sp_dc = sp_dc
        self._partner_token = None  # force re-exchange on next use

    # ----------------------------------------------------------------
    # Public API client (resolve only)
    # ----------------------------------------------------------------

    def _get_public_client(self) -> httpx.AsyncClient:
        if self._public_client is None:
            self._public_client = httpx.AsyncClient()
        return self._public_client

    async def close(self) -> None:
        for c in (self._public_client, self._partner_client):
            if c is not None:
                await c.aclose()
        self._public_client = None
        self._partner_client = None

    async def _ensure_token(self) -> str | None:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self._client_id or not self._client_secret:
            return None
        client = self._get_public_client()
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

        client = self._get_public_client()
        url = f"{_API_BASE}/{kind}s/{spotify_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 401:
                self._token = None
                log.warning("Spotify resolve 401 for %s/%s", kind, spotify_id)
                return None
            if resp.status_code != 200:
                try:
                    body = resp.text
                except Exception:
                    body = "<unreadable>"
                log.warning("Spotify resolve failed for %s/%s: %d — %s", kind, spotify_id, resp.status_code, body[:200])
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
        except httpx.HTTPError as exc:
            log.warning("Spotify resolve HTTP error for %s/%s: %s", kind, spotify_id, exc)
            return None

    # ----------------------------------------------------------------
    # Partner API token (sp_dc cookie exchange)
    # ----------------------------------------------------------------

    async def _get_sp_dc(
        self,
        session: Any,
        guild_id: int | None,
    ) -> str | None:
        """Get sp_dc cookie — env var first, fallback to guild_settings DB."""
        if self._sp_dc and self._sp_dc.strip():
            return self._sp_dc.strip()
        if guild_id is None:
            return None
        from stankbot.services.settings_service import Keys, SettingsService

        svc = SettingsService(session)
        raw = await svc.get(guild_id, Keys.SPOTIFY_SP_DC, None)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        self._sp_dc = str(raw).strip()
        return self._sp_dc

    async def can_fetch_metrics(
        self,
        session: Any,
        guild_id: int,
    ) -> bool:
        sp_dc = await self._get_sp_dc(session, guild_id)
        return sp_dc is not None

    async def _ensure_partner_token(
        self,
        session: Any | None = None,
        guild_id: int | None = None,
    ) -> str | None:
        if self._partner_token and time.time() < self._partner_token_expires_at - 60:
            return self._partner_token

        sp_dc = await self._get_sp_dc(session, guild_id)
        if not sp_dc:
            return None

        client = self._get_public_client()
        try:
            resp = await client.get(
                _PARTNER_TOKEN_URL,
                params={"reason": "transport", "productType": "web-player"},
                headers={
                    "User-Agent": _BROWSER_UA,
                    "origin": "https://open.spotify.com",
                    "referer": "https://open.spotify.com/",
                    "Cookie": f"sp_dc={sp_dc}",
                },
                timeout=10.0,
            )
            if resp.status_code == 403:
                log.warning("Spotify Partner token exchange blocked (WAF); sp_dc may be expired")
                return None
            if resp.status_code != 200:
                try:
                    body = resp.text
                except Exception:
                    body = "<unreadable>"
                log.warning("Spotify Partner token exchange failed: %d — %s", resp.status_code, body[:200])
                return None

            data: dict[str, Any] = resp.json()
            token = data.get("accessToken")
            if not token:
                log.warning("Spotify Partner token exchange: no accessToken in response — %s", list(data.keys()))
                return None

            self._partner_token = token
            expires_in = data.get("accessTokenExpirationTimestampMs", 0)
            if expires_in:
                self._partner_token_expires_at = float(expires_in) / 1000.0
            else:
                self._partner_token_expires_at = time.time() + 3600

            return self._partner_token
        except httpx.HTTPError as exc:
            log.warning("Spotify Partner token exchange error: %s", exc)
            return None

    # ----------------------------------------------------------------
    # Partner API client (browser-mimicking)
    # ----------------------------------------------------------------

    def _get_partner_client(self) -> httpx.AsyncClient:
        if self._partner_client is None:
            self._partner_client = httpx.AsyncClient(
                headers={
                    "User-Agent": _BROWSER_UA,
                    "origin": "https://open.spotify.com",
                    "referer": "https://open.spotify.com/",
                    "accept": "application/json",
                    "accept-language": "en",
                    "dnt": "1",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                }
            )
        return self._partner_client

    async def _ensure_client_token(self) -> str | None:
        """Extract the client-token from the web player JS bundle.

        Fetches open.spotify.com, finds the web player <script> tag,
        downloads the JS, and regexes out the client-token constant.
        Falls back to searching inline scripts on the page.
        Caches in memory; re-extracts if not yet fetched.
        """
        if self._client_token:
            return self._client_token

        async with self._client_token_lock:
            if self._client_token:
                return self._client_token

            client = self._get_partner_client()
            try:
                # 1. Get the landing page
                resp = await client.get("https://open.spotify.com/", timeout=15.0)
                if resp.status_code != 200:
                    log.warning("Failed to fetch open.spotify.com: %d", resp.status_code)
                    return None

                body = resp.text

                # 2. Try to find client-token in inline scripts first
                inline_ct = _CLIENT_TOKEN_RE.search(body)
                if inline_ct:
                    self._client_token = inline_ct.group(1)
                    log.info("Spotify: extracted client-token from inline script (len=%d)", len(self._client_token))
                    return self._client_token

                # 3. Find the web player JS bundle URL — try multiple patterns
                bundle_urls: list[str] = []

                # Pattern A: open.scdn.co web-player bundles (historical)
                for m in re.finditer(r'src="(https://open\.scdn\.co/[^"]*\.js)"', body):
                    bundle_urls.append(m.group(1))

                # Pattern B: any Spotify CDN JS bundle
                for m in re.finditer(r'src="(https://[^"]*spotify[^"]*cdn[^"]*\.js)"', body):
                    bundle_urls.append(m.group(1))

                # Pattern C: generic <script> with crossorigin attribute on Spotify domains
                for m in re.finditer(
                    r'<script[^>]*src="(https://[^"]*\.spotify(?:cdn)?\.(?:com|co)[^"]*)"[^>]*>',
                    body,
                ):
                    url = m.group(1)
                    if url not in bundle_urls:
                        bundle_urls.append(url)

                if not bundle_urls:
                    # Debug: log the first 2000 chars of script tags found
                    script_tags = re.findall(r'<script[^>]*src="[^"]*"[^>]*>', body)
                    log.warning(
                        "Could not find web player JS bundle. Script srcs found: %s",
                        script_tags[:5] if script_tags else "<none>",
                    )
                    return None

                # 4. Try each bundle URL until we find the client-token
                for bundle_url in bundle_urls:
                    try:
                        log.info("Spotify: trying bundle: %s", bundle_url[:120])
                        bundle_resp = await client.get(bundle_url, timeout=30.0)
                        if bundle_resp.status_code != 200:
                            continue

                        ct_match = _CLIENT_TOKEN_RE.search(bundle_resp.text)
                        if ct_match:
                            self._client_token = ct_match.group(1)
                            log.info(
                                "Spotify: extracted client-token from bundle (len=%d)",
                                len(self._client_token),
                            )

                            # Also extract app version
                            av_match = _APP_VERSION_RE.search(bundle_resp.text)
                            if av_match:
                                self._app_version = av_match.group(1)

                            return self._client_token
                    except httpx.HTTPError:
                        continue

                log.warning("Could not find clientToken in any web player bundle")
                return None

            except httpx.HTTPError as exc:
                log.warning("Spotify client-token extraction error: %s", exc)
                return None

    async def _partner_query(
        self,
        operation_name: str,
        variables: dict[str, object],
        sha256_hash: str,
    ) -> dict[str, Any] | None:
        """Execute a persisted GraphQL query against api-partner.spotify.com."""
        partner_token = await self._ensure_partner_token(self._session, self._session_guild_id)
        if not partner_token:
            log.warning("Spotify Partner API: no partner token available")
            return None

        client_token = self._client_token
        if not client_token:
            log.warning("Spotify Partner API: no client-token available")
            return None

        client = self._get_partner_client()
        headers = {
            "authorization": f"Bearer {partner_token}",
            "client-token": client_token,
            "app-platform": "WebPlayer",
            "spotify-app-version": self._app_version,
            "content-type": "application/json;charset=UTF-8",
        }
        payload = {
            "variables": variables,
            "operationName": operation_name,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256_hash,
                }
            },
        }

        try:
            resp = await client.post(
                _PARTNER_BASE,
                json=payload,
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 401:
                self._partner_token = None
                log.warning("Spotify Partner API: 401 — partner token may be expired")
                return None
            if resp.status_code != 200:
                try:
                    body = resp.text
                except Exception:
                    body = "<unreadable>"
                log.warning(
                    "Spotify Partner API %s failed: %d — %s",
                    operation_name,
                    resp.status_code,
                    body[:300],
                )
                return None
            data: dict[str, Any] = resp.json()
            if "errors" in data:
                log.warning("Spotify Partner API %s returned errors: %s", operation_name, data["errors"])
                return None
            return data
        except httpx.HTTPError as exc:
            log.warning("Spotify Partner API HTTP error (%s): %s", operation_name, exc)
            return None

    # ----------------------------------------------------------------
    # Metrics (Partner API: queryArtistOverview → playcount)
    # ----------------------------------------------------------------

    async def fetch_metrics(
        self,
        external_ids: list[str],
        metadata: dict[str, dict[str, object]] | None = None,
    ) -> list[MetricResult]:
        """Fetch playcount via Partner API queryArtistOverview.

        Requires metadata mapping external_id → {"artist_id": "..."} to
        group tracks by artist and issue one queryArtistOverview per artist.
        Tracks without an artist_id default to playcount=0.
        """
        results: list[MetricResult] = []

        # No session means we were called without the scheduler/DB context.
        # Return zero playcounts — the caller must pass a session via the
        # scheduler path (media_service uses the refresh_all session).
        if not external_ids:
            return results

        # Group by artist_id from metadata
        artist_tracks: dict[str, list[str]] = {}  # artist_id → [track_ids]
        orphan_ids: list[str] = []

        if metadata:
            for eid in external_ids:
                m = metadata.get(eid)
                artist_id = m.get("artist_id") if m else None
                if artist_id and isinstance(artist_id, str):
                    artist_tracks.setdefault(artist_id, []).append(eid)
                else:
                    orphan_ids.append(eid)
        else:
            orphan_ids.extend(external_ids)

        # Tracks without artist metadata → playcount 0
        for eid in orphan_ids:
            results.append(MetricResult(external_id=eid, values={"playcount": 0}))

        if not artist_tracks:
            return results

        # We need a session for the user token. The scheduler calls
        # refresh_all() with an active session, but fetch_metrics doesn't
        # receive it directly. We'll attempt token refresh without a session
        # if the cached user_token is still valid; otherwise fail gracefully.
        # We stash the session from the caller via a context var or instance
        # attribute. For now, try with the cached token first.
        for artist_id, track_ids in artist_tracks.items():
            data = await self._partner_query(
                operation_name="queryArtistOverview",
                variables={
                    "uri": f"spotify:artist:{artist_id}",
                    "locale": "",
                    "preReleaseV2": False,
                },
                sha256_hash=_ARTIST_OVERVIEW_SHA256,
            )

            if data is None:
                for eid in track_ids:
                    results.append(MetricResult(external_id=eid, values={"playcount": 0}))
                continue

            # Parse playcount from the response
            track_playcounts: dict[str, int] = {}
            try:
                top_tracks = (
                    data.get("data", {})
                    .get("artistUnion", {})
                    .get("discography", {})
                    .get("topTracks", {})
                    .get("items", [])
                )
                for item in top_tracks:
                    track = item.get("track", {})
                    tid = track.get("id")
                    raw_count = track.get("playcount")
                    if tid and raw_count is not None:
                        try:
                            track_playcounts[tid] = int(raw_count)
                        except (ValueError, TypeError):
                            track_playcounts[tid] = 0
            except Exception:
                log.warning("Failed to parse queryArtistOverview response for artist %s", artist_id)

            for eid in track_ids:
                count = track_playcounts.get(eid, 0)
                results.append(MetricResult(external_id=eid, values={"playcount": count}))

        return results

    async def health_check(self) -> bool:
        token = await self._ensure_token()
        return token is not None
