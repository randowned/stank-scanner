![](static/Stank.gif)

# StankBot

**StankBot** is a Discord Application that tracks "Stank" sticker chains in community servers. It runs as a real bot user with slash commands, durable storage, per-server configuration, and a web dashboard.

## What the bot does

Players cooperate to build the longest chain of a designated sticker in a designated channel (the **altar**). The chain breaks when anyone posts a non-sticker message. Players earn Stank Points (SP) for contributing; breaking the chain costs SP.

Rankings are **net SP** (earned SP minus SP lost to breaks).

| Action | Points |
|---|---|
| Chain starter (first stank in a new chain) | +10 SP base + 15 SP starter bonus |
| Each subsequent stank at position *N* | +10 SP base + (N−1) SP position bonus |
| Last contributor when a chain breaks (not the breaker) | +15 SP finish bonus |
| Last stank of one shift + first stank of the next (chain must survive the rollover) | +20 SP Team Player bonus |
| React to an in-chain sticker with the altar emoji | +1 SP (once per user per message) |
| Break the chain | −(25 + chain_length × 2) SP |

All values are per-guild defaults, editable on the web dashboard. The same user cannot stank twice within the configurable cooldown (default 20 minutes).

Sessions roll over on a cron (default 07:00 / 15:00 / 23:00 UTC) with configurable warning minutes. Chain continuity across sessions is on by default — the live chain survives the session boundary. Per-user cooldowns reset at the rollover so the same player can be last-of-shift and first-of-next for a Team Player bonus.

## Feature highlights

- **Slash commands only.** Every user reply is ephemeral unless it's an announcement.
- **Rich embed rendering** for the board, record announcements, and session transitions — no ASCII code blocks.
- **Multi-guild from day one.** Every row keyed by guild id.
- **Event-sourced.** Every SP/PP change is an immutable event row. Player totals, session summaries, and records are derived — `rebuild-from-history` can always reconstruct them.
- **Multi-altar per guild.** Run a themed event (Halloween sticker, Founders Day) alongside the normal chain with its own scoring overrides and a `custom_event_key` tag on every emitted event.
- **Achievements / badges** derived from the event log — First Stank, Centurion, Finisher, Chainbreaker, Comeback Kid, Perfect Session, Streaker, Team Player.
- **Web dashboard** with Discord OAuth — public board with reaction-aware leaderboard (live reorder + delta chips + chain-break overlay), player profiles with 30-day sparklines + achievement gallery, session history, and a five-page admin surface (Dashboard · Templates · Admins · Audit · Settings with embedded session ops). MsgPack-first transport over HTTP + WebSocket. SvelteKit SPA served at `/`.
- **Media analytics** for YouTube and Spotify. Add videos/albums via the admin panel, view metric history and comparison charts on the dashboard, and query stats in Discord with `/stats youtube info <name>` / `/stats spotify info <name>` / `/stats youtube chart <name> [type] [range]`. Per-provider embed templates, scheduled metric snapshots, configurable refresh intervals, public chart image endpoint, and configurable milestone announcements at every 1M views/plays through 50M then 75M / 100M / 150M / ... / 1B — with celebratory embeds pushed to announcement channels. Spotify playcount is fetched via the Partner API using the bot owner's connected account (OAuth PKCE flow in Settings).

## Running it yourself

### Local dev (mock mode — no Discord needed)

For frontend work and E2E testing, run in **mock mode** with a fake Discord backend:

```powershell
# Windows
.\scripts\dev.ps1

# macOS / Linux
./scripts/dev.sh
```

This starts the backend (`ENV=dev-mock`, reads `.env.dev-mock`) and the Vite dev server on `http://localhost:5173`. The dashboard auto-logs you in as a mock user.

Requires Python 3.12 and [`uv`](https://github.com/astral-sh/uv):

```powershell
winget install Python.Python.3.12
winget install astral-sh.uv
git clone <this-repo>
cd stank-bot
uv venv
uv sync
uv run alembic upgrade head   # only needed once
```

### Local dev (real Discord)

If you need the real Gateway connection (testing bot logic):

```powershell
cp .env.example .env.dev   # fill in tokens
$env:ENV="dev"
uv run python -m stankbot
```

The bot connects outbound to Discord's Gateway (WebSocket over 443) — no inbound ports, no public URL, no tunnel needed. The dashboard binds to `127.0.0.1:8000` by default.

### Linux VPS (systemd)

`deploy/systemd/stankbot.service` runs `python -m stankbot` in a project-local venv with `EnvironmentFile=/etc/stankbot/stankbot.env` for secrets. Works with either root systemd (`/etc/systemd/system/`) or user systemd (`~/.config/systemd/user/` + `loginctl enable-linger`).

### Docker

```
docker compose up -d
```

Data persists in `./data/` (SQLite by default).

### Railway (auto-deploy from GitHub)

`railway.json` at the repo root points Railway at `deploy/docker/Dockerfile`. Every push to `main` triggers a build and rolling deploy. One-time setup in the Railway UI:

1. New project → Deploy from GitHub repo → pick this repo, branch `main`.
2. Add a **Volume** mounted at `/data` — the Dockerfile already bakes `DATABASE_URL=sqlite+aiosqlite:////data/stankbot.db` against it, so SQLite survives redeploys.
3. Set the same env vars you use locally: `DISCORD_TOKEN`, `DISCORD_APP_ID`, `WEB_SECRET_KEY`, `OAUTH_CLIENT_SECRET`, `GUILD_IDS`, etc.
4. Expose port `8000`; Railway mints a public URL for the dashboard. Add `<that URL>/auth/callback` to the Discord OAuth2 redirects list.
5. Keep replicas at **1** — Discord only allows one gateway connection per shard.

Deploys are gated on the `/healthz` endpoint, which returns 200 only when the DB is reachable and the Discord client is `is_ready()`. On redeploy, Railway sends SIGTERM; the bot cancels scheduled jobs, closes the gateway cleanly, and disposes the engine before exiting. APScheduler jobs are rebuilt from guild settings on each boot, so no schedule state is lost.

## Creating the bot user

1. Discord Developer Portal → Applications → StankBot (App ID `1494266000064122930`).
2. **Bot** → *Reset Token* → copy into `DISCORD_TOKEN`.
3. Enable **Message Content Intent** and **Server Members Intent**. Presence intent is off.
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permissions Send Messages, Embed Links, Read Message History, Add Reactions, Use External Stickers, Manage Messages.
5. Open the generated URL, pick your guild, authorize.
6. In the Developer Portal, add your dashboard URL + `/auth/callback` to **OAuth2 → Redirects** so web login works.
7. Leave the **Interactions Endpoint URL** field empty — the bot uses the Gateway, not webhook interactions.

## Configuration

Environment (see `.env.example`):

| Var | Purpose |
|---|---|
| `DISCORD_TOKEN` | Bot token |
| `DISCORD_APP_ID` | Application id (default `1494266000064122930`) |
| `DATABASE_URL` | SQLAlchemy URL, e.g. `sqlite+aiosqlite:///./data/stankbot.db` |
| `OWNER_ID` | Your Discord user id — superadmin across all guilds |
| `OWNER_DEFAULT_GUILD_ID` | Guild presented to all players on the web dashboard (overrides first `GUILD_IDS` entry) |
| `LOG_LEVEL` | `INFO` / `DEBUG` |
| `LOG_FORMAT` | Log output format: `text` or `json` (default: `text`) |
| `ENABLE_WEB` | `true` to run the dashboard in the same process |
| `WEB_BIND` | Dashboard bind, single `host:port` string (default `127.0.0.1:8000`) |
| `OAUTH_CLIENT_SECRET` / `OAUTH_REDIRECT_URI` | Dashboard login (OAuth client id is `DISCORD_APP_ID`) |
| `GUILD_IDS` | Comma-separated guild ids for slash sync; first entry is fallback default |
| `WEB_SECRET_KEY` | Cookie signing secret for the dashboard |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key for media metrics |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Spotify app credentials for media metrics and OAuth |
| `SPOTIFY_OAUTH_REDIRECT_URI` | Spotify OAuth callback URL (e.g. `https://stank.bot/auth/spotify/callback`) |
| `CHART_CACHE_DIR` | Directory for cached `/api/media/{id}/chart` PNGs (default `/data/media/chart`); cleaned every 10 minutes by the media scheduler. |

**Dev-only mocks** (`.env.dev`, no secrets needed):

| Var | Purpose |
|---|---|
| `ENV=dev` | Activates dev mode |
| `MOCK_DISCORD=true` | Skip Gateway; bot logic runs against fake events |
| `MOCK_AUTH=true` | Skip OAuth; auto-login as `MOCK_DEFAULT_USER_NAME` |
| `MOCK_DEFAULT_GUILD_ID` | Fake guild id for local testing |
| `MOCK_AUTO_EVENTS` | Inject random stanks/breaks automatically |

Scoring tuning, reset hours, embed templates, feature toggles, altar wiring, and admin management all live on the web dashboard — no slash commands for any of it.

## First-time guild setup

All setup happens on the web dashboard (log in with Discord OAuth):

- `/admin/settings` — altar channel + sticker pattern + reaction emoji, scoring, reset hours, announcement channels, maintenance toggle, plus session operations (new session / reset / rebuild) in the sticky side rail
- `/admin/admins` — add admin roles or users (roles per-guild, users global)

## Command reference

### User (`/stank …`)

| Command | What it does |
|---|---|
| `/stank board` | Rich embed of the current chain, records, rankings. |
| `/stank points [rank] [user]` | Your (or target's) SP / PP / chains / badges. |
| `/stank cooldown` | Seconds left before you can stank again. |
| `/stank help` | Rules + scoring table. |
| `/stank history me` | Your per-session trend. |
| `/stank history user <user>` | Same for a target user. |
| `/stank history chain <id>` | Chain replay. |
| `/stank history session <id>` | Session summary. |

### Media (`/stats …`)

| Command | What it does |
|---|---|
| `/stats youtube info <name>` | Rich embed with full-number metrics, day-over-day deltas, formatted dates/durations, and cover photo. |
| `/stats spotify info <name>` | Rich embed with latest Spotify track/album metrics and day-over-day playcount change. |
| `/stats youtube chart <name> [type] [range] [mode] [resolution] [compare1] [compare2] [compare3]` | Inline chart image (16:9 PNG) for views, likes, or comments. Defaults: Views / 24h / Delta / Hourly. `resolution` buckets data (5min/15min/30min/hourly/daily/weekly/monthly); auto-selected when omitted. Add up to 3 `compare` names for a multi-series comparison chart. |
| `/stats spotify chart <name> [type] [range] [mode] [resolution] [compare1] [compare2] [compare3]` | Inline chart image for playcount. Defaults: Playcount / 24h / Delta / Hourly. `resolution` buckets data; auto-selected when omitted. Add up to 3 `compare` names for a multi-series comparison chart. |

Admins can disable individual media providers per-guild from the media settings panel; non-admins won't see disabled-provider items, while admins always see everything (so they can re-enable). The dashboard detail page exposes a `Resolution` dropdown (Auto / 5 Min / 15 Min / 30 Min / Hour / Day / Week / Month) filtered by the selected range and the provider's configured poll interval (resolutions finer than the poll interval are hidden). Auto resolution targets ~24 data points for the selected range (e.g. 1 day → hourly). All resolutions select exactly-aligned snapshots via bitmask for accurate delta and total values; the Discord chart-image endpoint uses the same auto-aggregation logic. Snapshot intervals are per-provider (YouTube / Spotify), configurable from 1 min to 24 hours (default 60 min).

All `/stats` commands support autocomplete on the `name` parameter. Admin guilds can restrict access via the media settings panel (`admin-only` toggle).

### Admin (`/preview`) — requires admin role or Manage Guild

| Command | What it does |
|---|---|
| `/preview` | Ephemeral preview of record, chain, session, cooldown, or media milestone embeds. |

Every other admin action (altar wiring, scoring, reset, rebuild, announcements, admin users/roles, maintenance) lives on the web dashboard at `/admin/*`.

CLI alternative for rebuild: `python -m stankbot.rebuild --guild-id <id>`.

## Web dashboard

The dashboard is a PWA — installable from Chrome / Edge via the address bar or settings menu. No automatic install prompt.

- `/` — landing page for unauthenticated visitors (Discord login CTA); authenticated users see the full leaderboard + chain state board instead. Top tiles: **Reactions** (current chain, chain-scoped) · Current · Session · All-time. Leaderboard rows live-reorder on point changes with floating `+N` delta chips and show net SP (`+N SP` / `-N SP`) with stanks and reactions counts. A chain break paints an overlay with the breaker and SP loss until the next chain starts. Starter / Breaker quick-link cards below the tiles.
- `/me` → `/player/{user_id}` — stats with avatar + rank badge, session and all-time SP/PP, stank-streak tracker (current + longest), 30-day sparklines, recent chain participation list, and achievement gallery.
- `/sessions` — historical session list with start/end times, duration, stank/reaction/chain counts, and total SP/PP per session.
- `/session/{id}` — session summary with computed duration, total SP/PP awarded, top-5 session leaderboard with avatars, and per-chain breakdown (open / broken / rollover).
- Admin surface (six pages):
  - `/admin` — dashboard tiles + top stats.
  - `/admin/templates` — live JSON editor for embed templates (stored in `data/templates/`).
  - `/admin/admins` — admin roles (per-guild) + global admin users.
  - `/admin/audit` — admin action audit trail.
  - `/admin/events` — game event log (stanks, breaks, reactions, achievements).
  - `/admin/settings` — two-column page: left lists Altar / Scoring / Behavior / Reset windows / Announcements / Maintenance cards; right sticky rail holds New Session · Reset · Rebuild.
- `/media` — media dashboard: provider type tabs (All / YouTube / Spotify) with colored left borders, provider-aware card grid (Spotify cards show playcount, duration, and release year; YouTube cards show views, likes, comments), search bar, sort dropdown, compare mode (select 2+ items via whole-card click — cross-type items are auto-disabled — to navigate to a detail page with comparison charts via `?compare=` query param).
- `/media/{id}` — single media item detail: provider-aware metric tiles (1 tile for Spotify, 3 for YouTube), time-scale history chart with range options (1h / 6h / 12h / 24h / 48h / 7d / 30d / 90d / 1y, default 48h), defaults to Change (delta) mode, view mode toggle (Change / Cumulative — title updates to "{metric} cumulative" in Cumulative mode) with alignment-filtered rendering (5 Min / 15 Min / 30 Min / Hourly / Daily / Weekly / Monthly resolution, range-filtered to require ≥2 buckets), data-start indicator when data is shorter than selected range, multi-series comparison overlay (type-filtered), staleness pill in header, "Open on YouTube / Spotify" link in metadata sidebar, chart legend uses item name instead of full title, sparse-data hint when only one snapshot exists, gap-free line rendering. All chart controls (metric, range, resolution, mode, compare IDs) are reflected in the URL query string — share or reload preserves the exact chart view. History and comparison data are served in a single API call via the unified `/api/media/{id}/history?compare_ids=...` endpoint.
- Admin `/admin/media` — manage media: add (tabbed by provider, optional name), client-side type filter (no API reload on tab switch), colored provider badges (YouTube red, Spotify green), force-refresh single or all, settings modal with per-provider interval dropdowns (YouTube / Spotify, 1min–24h) + ephemeral replies toggle + admin-only toggle + milestone announcement toggle + additional media channel ID + alignment mask backfill button, mobile-friendly rows with edge-to-edge thumbnails. Mobile-optimized modal with scrollable content.
- Admin `/admin/media/{id}/edit` — edit page: editable name field with save, metadata summary, and last 20 metric snapshots in a pivoted table (all metrics side by side per timestamp).
- Header: single row, `Live updates` badge for non-admin users (gray when logged out, green/muted/red when connected) or `N online` badge for admin users (clickable popover with avatars + session durations), user menu with Navigate (Dashboard / Sessions / Media) + My Profile + collapsible Switch Guild showing the active guild's icon + name.
- `/chain/{id}` — chain detail with status banner (alive / broken / rollover), length classification (Short / Medium / Long / Epic), per-position timeline (avatar + position badge + SP awarded at each stank), and per-user leaderboard with stank and reaction counts.
- Auth guard: unauthenticated requests to any non-public route redirect to `/`. All data API endpoints require guild membership (`require_guild_member`).

