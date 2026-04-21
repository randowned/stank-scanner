![](static/Stank.gif)

# StankBot

**StankBot** is a Discord Application that tracks "Stank" sticker chains in community servers. It runs as a real bot user with slash commands, durable storage, per-server configuration, and a web dashboard.

## What the bot does

Players cooperate to build the longest chain of a designated sticker in a designated channel (the **altar**). The chain breaks when anyone posts a non-sticker message. Players earn Stank Points (SP) for contributing and Punishment Points (PP) for breaking chains.

Rankings are **net SP** (earned SP minus PP).

| Action | Points |
|---|---|
| Chain starter (first stank in a new chain) | +10 SP base + 15 SP starter bonus |
| Each subsequent stank at position *N* | +10 SP base + (N−1) SP position bonus |
| Last contributor when a chain breaks (not the breaker) | +15 SP finish bonus |
| Last stank of one shift + first stank of the next (chain must survive the rollover) | +20 SP Team Player bonus |
| React to an in-chain sticker with the altar emoji | +1 SP (once per user per message) |
| Break the chain | −(25 + chain_length × 2) PP |

All values are per-guild defaults, editable on the web dashboard. The same user cannot stank twice within the configurable cooldown (default 20 minutes).

Sessions roll over on a cron (default 07:00 / 15:00 / 23:00 UTC) with configurable warning minutes. Chain continuity across sessions is on by default — the live chain survives the session boundary. Per-user cooldowns reset at the rollover so the same player can be last-of-shift and first-of-next for a Team Player bonus.

## Feature highlights

- **Slash commands only.** Every user reply is ephemeral unless it's an announcement.
- **Rich embed rendering** for the board, record announcements, and session transitions — no ASCII code blocks.
- **Multi-guild from day one.** Every row keyed by guild id.
- **Event-sourced.** Every SP/PP change is an immutable event row. Player totals, session summaries, and records are derived — `rebuild-from-history` can always reconstruct them.
- **Multi-altar per guild.** Run a themed event (Halloween sticker, Founders Day) alongside the normal chain with its own scoring overrides and a `custom_event_key` tag on every emitted event.
- **Achievements / badges** derived from the event log — First Stank, Centurion, Finisher, Chainbreaker, Comeback Kid, Perfect Session, Streaker, Team Player.
- **Web dashboard** (FastAPI + Jinja2 + HTMX) with Discord OAuth — public board, player profiles, chain/session history, admin pages with live embed-template preview.

## Running it yourself

### Local dev (Windows)

Requires Python 3.12 and [`uv`](https://github.com/astral-sh/uv).

```powershell
winget install Python.Python.3.12
winget install astral-sh.uv
git clone <this-repo>
cd stank-bot
uv venv
uv sync
cp .env.example .env.local   # fill in tokens
uv run alembic upgrade head
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
3. Set the same env vars you use locally: `DISCORD_TOKEN`, `DISCORD_APP_ID`, `WEB_SECRET_KEY`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `GUILD_IDS`, etc.
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
| `OWNER_ID` | Your Discord user id — bypass permission checks |
| `LOG_LEVEL` | `INFO` / `DEBUG` |
| `ENABLE_WEB` | `true` to run the dashboard in the same process |
| `WEB_HOST` / `WEB_PORT` | Dashboard bind (defaults `127.0.0.1:8000`) |
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_REDIRECT_URI` | Dashboard login |
| `GUILD_IDS` | Comma-separated guild ids for instant slash sync during dev |
| `SESSION_SECRET` | Cookie signing secret for the dashboard |

Everything else — scoring tuning, reset hours, embed templates, feature toggles — lives on the web dashboard.

## First-time guild setup

```
/stank-admin altars add channel:#altar sticker:<sticker_id>
/stank-admin announcements add channel:#general
/stank-admin admin-roles add role:@Mods
/stank-admin rebuild-from-history        # optional — replay existing chat
```

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

### Admin (`/stank-admin …`) — requires admin role or Manage Guild

| Command | What it does |
|---|---|
| `/stank-admin dashboard` | Posts the dashboard URL for this guild. |
| `/stank-admin new-session` | End current session, start next; chain persists. |
| `/stank-admin reset` | Wipe chain / events / records (destructive, confirmation). |
| `/stank-admin rebuild-from-history` | Wipe + replay altar channel history (destructive). |
| `/stank-admin preview` | Ephemeral preview of record, chain, session, or cooldown embeds. |
| `/stank-admin log [lines]` | Tail recent bot log. |
| `/stank-admin config view` | Read-only snapshot of current settings. |
| `/stank-admin announcements add\|remove\|list` | Manage announcement channels. |
| `/stank-admin admin-roles add\|remove\|list` | Manage admin roles. |
| `/stank-admin altars add\|remove\|list` | Register / remove altars. |

Template bodies, scoring overrides, reset hours, and achievement tuning are web-only — `/stank-admin config view` surfaces the current values but does not edit them.

CLI alternative for rebuild: `python -m stankbot.rebuild --guild-id <id>`.

## Web dashboard


- `/` — public leaderboard + chain state.
- `/me` → `/player/{user_id}` — your stats, badges, history.
- `/history/chains` · `/history/chain/{id}` — chain browser + replay.
- `/history/sessions` · `/history/session/{id}` — session browser + summary.
- `/admin/settings` — scoring / reset / feature toggles; displays visual feedback (saved indicator) when settings are updated.
- `/admin/altar` · `/admin/roles` · `/admin/audit` — wiring + audit trail.

