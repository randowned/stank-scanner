---
description: Debug a production problem on Railway. Pulls logs, checks health, narrows to a subsystem.
argument-hint: <problem description>
---

Diagnose this production issue: $ARGUMENTS

Deployment target is Railway; the service runs as a single replica from `deploy/docker/Dockerfile` per `railway.json`.

## Steps

### 1. Frame the problem
Restate the symptom in one sentence. List 1–2 likely hypotheses before running any tools so the investigation stays focused.

### 2. Pull Railway state
Use the Railway CLI (or Railway MCP tooling if available):

- `railway status` — current service + environment, last deploy.
- `railway logs` — recent runtime logs. Scan for tracebacks, `ERROR`, `CRITICAL`, repeated reconnects, SIGTERM, OOM.
- `railway logs --deployment` — build/deploy logs if the symptom started right after a deploy.
- Hit `<public-url>/healthz` — returns 200 only when the DB is reachable and the Discord client is `is_ready()`. Failing healthcheck is why Railway restarts the container.

Filter to the last ~15 minutes or from the last deploy timestamp if logs are noisy.

### 3. Check operational invariants
Before going deep into code, rule out configuration drift:

- **Single replica only.** Discord allows one gateway connection per shard. Two replicas → login loops.
- **Volume mounted at `/data`.** SQLite at `sqlite+aiosqlite:////data/stankbot.db`. Detached volume → every redeploy wipes data and re-runs migrations from empty.
- **Port 8000** for the dashboard. Public URL must be in Discord OAuth2 redirects as `<url>/auth/callback`, otherwise login breaks.
- **Required env vars:** `DISCORD_TOKEN`, `DISCORD_APP_ID`, `WEB_SECRET_KEY`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `GUILD_IDS`.
- **Shutdown path:** on SIGTERM the bot cancels APScheduler jobs, closes the gateway, disposes the engine. Jobs are rebuilt from guild settings on next boot.
- **Restart policy:** `ON_FAILURE` max 10 retries. Exhausted retries → service stays down until next deploy.

### 4. Narrow to a subsystem
Based on the symptom, read the smallest relevant surface:

- **Chain / scoring:** `src/stankbot/services/chain_service.py`, `src/stankbot/services/scoring_service.py`.
- **Session boundaries:** `src/stankbot/services/session_service.py`.
- **Schema / migration:** `src/stankbot/db/models.py`, `migrations/`.
- **Embed / rendering:** `src/stankbot/services/board_renderer.py`, `src/stankbot/services/template_engine.py`.
- **Discord surface:** `src/stankbot/cogs/`.
- **Dashboard / OAuth:** `src/stankbot/web/routes/`, `src/stankbot/web/app.py`.
- **Boot / logging:** `src/stankbot/__main__.py`, `src/stankbot/logging_setup.py`.

### 5. Report
- Root cause (or best current hypothesis).
- Evidence from logs / code.
- Proposed fix — which files, what change.

Do **not** commit or push. If the user approves the fix, run `/commit-and-push` to ship.
