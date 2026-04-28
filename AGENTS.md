# AGENTS.md

Operational guide for AI agents (Claude Code, etc.) working in this repository. Keep this file current: update it when workflow rules or architecture change.

Procedures live in `.claude/commands/` (user-triggered) and `.claude/skills/` (auto-invoked). This file is the map — not the procedures themselves.

> **`.claude/` is a local symlink to `.opencode/`.** Both directories point to the same files. Do not create or edit anything under `.claude/` — always use `.opencode/` instead. The `.claude/settings.local.json` file is local-only and not tracked in git.

## Workflow rules

These rules override any default behavior. Follow them strictly.

### Branches
- **Only work on `main`, or on a branch the user explicitly names.** Never create, switch, rebase, or merge branches on your own. No worktrees — edit the files in place.
- **No pull requests.** Never run `gh pr create` or open a PR. The project ships directly from branches.
- **Save changes directly to files and stop.** Do not stage, do not commit. The user previews changes in another editor via its git integration, so unstaged edits are exactly what they want to see.

### Commits
- **🔴 UN-SKIPPABLE: Never commit, push, or bump the version unless the user explicitly asks.** After finishing a change, stop and wait. Even if you just shipped a version and made follow-up fixes, do NOT commit them unprompted. The user decides when to ship.
- Shipping is handled by `/commit-and-push` (version bump + README sync + commit + push). Docs-only sync is `/update-docs`.
- **Never auto-execute `/commit-and-push` or `/update-docs`** — these must only run when the user explicitly invokes them. If there are uncommitted/unstaged changes in the repo, do not commit, push, or bump without being told.
- **No `Co-Authored-By` trailer.** Never add AI co-author trailers. (Also enforced via `~/.claude/CLAUDE.md`.)

### Debugging production
- Prod issues on Railway: use `/triage <problem description>`. It pulls logs, checks `/healthz`, walks the invariants, and narrows to a subsystem.

### Subagents
Use subagents (the `Agent` tool with `Explore`, `Plan`, or `general-purpose`) when the work genuinely benefits from delegation.

**Use a subagent when:**
- Tracing a concept across many files (e.g. "how does the cooldown flow from ChainService through the repositories and into the embed").
- Designing a non-trivial change that touches services + cogs + DB together — spawn a `Plan` agent to validate the approach before editing.
- Running independent investigations in parallel so the main context stays clean.
- Using a tool whose output is noisy or large that would otherwise bloat context for little signal.

**Don't use a subagent for:**
- Edits to a known function at a known line.
- One-shot greps or reads you can do directly with `Grep`/`Read`.
- "Find this string" tasks — use `Grep` directly.

When delegating, brief the agent self-contained: state the goal, name the files/symbols already known, and cap the response length. Never ask a subagent to commit, push, or open PRs.

### Other defaults
- Stay inside the repo; don't touch external systems without being asked.
- Prefer editing existing code to adding new files. The project is intentionally multi-file, but resist inventing new modules when an existing one is the right home.
- Do not invent abstractions (base classes, plugin interfaces, DI frameworks) until a second concrete implementation forces the shape.
- **Use git-bash** (`"C:\Program Files\Git\bin\bash.exe" -c "..."`) instead of PowerShell for all command execution. PowerShell has quirks with `&&`, environment variable inheritance, and process management that git-bash avoids.
- **Track PIDs, never kill by process name.** When you start a background process (backend, frontend dev server), save its PID: `echo $! > /tmp/backend.pid`. Kill only by PID: `kill $(cat /tmp/backend.pid)`. Killing by `python.exe` or `node.exe` may terminate unrelated developer tools (VS Code, other projects' servers, etc.).
- **Restarting processes.** When backend or frontend changes don't take effect, stale processes may be running from previous bash sessions. Kill them by tracked PID. The Vite dev server caches compiled components in memory; if E2E tests behave inconsistently after editing `.svelte` files, kill the Node process so the dev server recompiles fresh on next startup.

### Database migrations

When creating an Alembic migration, the `down_revision` must point to the actual current head in `migrations/versions/`. The migration chain has broken twice (`v2.26.1`, `v2.26.2`) from an incorrect `down_revision`. Run `alembic history` before creating a new migration to confirm the latest head's revision ID.

### Environments

| Mode | Env file | Discord | Auth | Purpose |
|------|----------|---------|------|---------|
| `dev` | `.env.dev` | Real token | Real OAuth | Local development with real Discord |
| `dev-mock` | `.env.dev-mock` | Mocked (`mock_discord=true`) | Mocked (`mock_auth=true`) | Local development, manual testing, E2E (no credentials needed) |
| `production` | System env / Railway | Real token | Real OAuth | Live deploy |

- `.env.dev` holds real credentials (not committed). Use `ENV=dev` for real Discord testing.
- `.env.dev-mock` is committed (no secrets) and uses a separate SQLite DB (`stankbot_dev.db`).
- Never enable `mock_discord` or `mock_auth` outside `ENV=dev-mock`. The code gates these with `if config.env == "dev-mock"`; respect that invariant.

## Testing

All changes must be verified before they are considered done. The verification path depends on what you changed.

### Backend changes (services/, cogs/, db/, web/)

1. **Unit tests:** `pytest` (or `pytest tests/unit/test_xxx.py` for the subsystem).
2. **Lint & typecheck:** `ruff check src tests` and `mypy src`. Do not introduce new failures.
3. **Dev mode smoke test:** Start dev mode (`ENV=dev`), open `http://localhost:5173`, and confirm the feature works end-to-end.
4. **E2E coverage:** If the change touches a user-facing dashboard flow and no E2E test covers it, **you must add one**.

### Frontend changes (src/stankbot/web/frontend/src/)

1. **Typecheck & lint:** `cd src/stankbot/web/frontend && npm run check && npm run lint`. Do not introduce new failures.
2. **Dev mode smoke test:** Start dev mode, verify the UI visually and via network tab.
3. **E2E coverage:** Same rule as backend — if no E2E test covers the modified flow, **you must add one**.

### Frontend patterns

**Framework stack.** SvelteKit 2 with `@sveltejs/adapter-static` (SPA mode, no SSR). Svelte 5 runes (`$state`, `$derived`, `$effect`) in `.svelte` files. Traditional `writable` stores from `svelte/store` for cross-component state (board, auth, toasts, WS events).

**Svelte 5 lifecycle quirk — `bind:this` is not available in `onMount`.** In Svelte 5, element bindings (`bind:this={el}`) resolve after `onMount` runs. To access a bound element reference, use `$effect` + `tick()`:
```typescript
let btn: HTMLButtonElement;
$effect(() => {
    tick().then(() => {
        if (!btn) return;
        btn.addEventListener('click', handler);
    });
});
```

**Svelte 5 event delegation.** `onclick` (not `on:click`) is the correct syntax in runes mode, but Svelte 5 uses event delegation under the hood. If delegated events don't fire (e.g. in E2E tests with Playwright), fall back to native DOM via `$effect` + `tick()` + `addEventListener`. The `OnlineBadge` component is a reference example of this pattern.

**API calls MUST use `apiFetch`**, not `fetch`. The custom `apiFetch` wrapper in `src/lib/api.ts` negotiates msgpack encoding for request body and response parsing. The same `Packr` instance is shared with the WebSocket client for consistent binary encoding. The `loadWithFallback` wrapper in `src/lib/api-utils.ts` handles page load errors gracefully — use it in `+page.ts` load functions instead of try/catch. The `toErrorMessage` helper in the same file standardizes error message extraction from `FetchError` and other error types — use it instead of repeated `err instanceof FetchError ? err.message : 'Fallback'` patterns.

**Auth state is cached in sessionStorage** under keys `stankbot:auth` and `stankbot:guilds`. After login/logout, these caches must be cleared (the `mockLogin` fixture does this automatically). The `+layout.ts` root layout fetches `/auth` and `/api/guilds` once per SPA navigation and caches the results.

**Reusable components** live in `$lib/components/` — use existing ones (`Button`, `Input`, `Toggle`, `Dropdown`, `Modal`, `Tabs`, `Avatar`, `StatTile`, `RemovableItem`, `ToastContainer`, `GuildSwitcher`, etc.) before creating new ones. Every component should use `data-testid` attributes for stable E2E queries. The `StatTile` component accepts a `valueTestId` prop when the inner value `<div>` needs its own test ID (e.g. `data-testid="chain-counter"`). The root `+page.svelte` delegates to `WelcomePage` (unauthenticated) or `Dashboard` (authenticated) — do not inline landing/dashboard logic in the route file.

**WebSocket connection lifecycle** is managed in `src/lib/ws.ts`. It auto-reconnects with exponential backoff, deduplicates connections, and dispatches events to the `lastWsEvent` store (see `src/lib/stores/ws-events.ts`). The store pattern is: `emitWsEvent({ kind: '...', ... })` → layout subscribes and reacts. Do not create additional WS connections — use the existing one.

**Stores** in `src/lib/stores/` are the single source of truth for:
- `boardState` — leaderboard rankings, chain state, reactions
- `connectionStatus` — WS connection state
- `lastWsEvent` — side-channel events (toasts, achievements, version mismatch)
- `toasts` — notification queue (auto-dismiss after 3s)
- `guildId` / `user` / `guilds` — auth state hydrated from `+layout.ts` load function
- `adminSidebarOpen` — admin sidebar toggle
- `activeChainBreak` — chain break overlay state
- `onlineUsers` — online admin users list with session durations

**Common pitfalls from historical fixes:**
- SPA navigation does NOT reload stores (`+layout.ts`). Auth/board data is cached until a manual reload or explicit refetch (v2.19.1).
- WS connections must be deduplicated — guard with `ws?.readyState === WebSocket.OPEN` before creating (v2.17.14).
- The Vite dev server proxies `/api`, `/ws`, `/auth`, `/ping` to the backend at `localhost:8000`. If the backend isn't running, all API calls fail silently or return `ECONNREFUSED`.
- When adding a new store, export it from `src/lib/stores/index.ts` so `$lib/stores` resolves it.
- The `playerProfiles`, `loading`, and `cache` stores were deleted in v2.29.2. Player data loads per-page via `+page.ts`. Use local `$state` for loading flags — the global loading counter store is gone.
- `formatNumber()` and `formatDuration()` live in `$lib/format.ts` — use them instead of redefining the M/K suffix or `XhYm` duration logic.

### E2E test execution

**Primary: `npm run e2e`.** This single command (`scripts/run-e2e.mjs`) starts the backend (health-check polling via `/healthz` on port 8000, logs → `.stankbot_backend.log`), runs Playwright, and cleans up on exit. Backend output is buffered to a file so test results stay clean.

When iterating on a running dev server: `npm run test:e2e` (backend already up). The `mockLogin` fixture's `waitForBackend()` guard polls `/ping` for 10s first, giving a clear error if the backend is absent.

### E2E test patterns

**DB state pollution.** The SQLite DB (`stankbot_dev.db`) persists between E2E test runs. Hardcoded user IDs accumulate SP/PP across runs, causing flaky assertions on exact values. Use unique-per-run user IDs (`Date.now() % 1_000_000_000` or a counter-based `makeId()`) when the specific SP value matters, not just that it's truthy. Fixtures like `newSession()` break the chain and end the session but do NOT clear event history.

**Playwright WebSocket frame interception.** To capture server-to-client WS frames in Playwright:
```typescript
const frames: Buffer[] = [];
page.on('websocket', (ws) => {
    ws.on('framereceived', (frame) => {
        if (frame.payload instanceof Buffer) frames.push(frame.payload);
    });
});
```
- Use `'framereceived'` event (fires per message), NOT `'frames'` (may not fire reliably).
- For msgpack binary frames, `frame.payload` is a Buffer; decode with `msgpackr.unpack(new Uint8Array(buf))`.
- Set up the handler BEFORE calling `page.reload()` or `page.goto()` so it catches the WS connection.

### Mock event injection

When verifying in `ENV=dev-mock`, use the mock API to drive state changes without Discord:

| Endpoint | Action |
|----------|--------|
| `POST /api/mock/stank` | Inject a valid stank |
| `POST /api/mock/break` | Inject a chain break |
| `POST /api/mock/reaction` | Inject a reaction bonus |
| `POST /api/mock/noise` | Inject a non-stank message (breaks chain) |
| `POST /api/mock/session/start` | Start a new session |
| `POST /api/mock/session/end` | End current session |
| `POST /api/mock/random/start` | Start auto-generated events |
| `POST /api/mock/random/stop` | Stop auto-generated events |

These endpoints are **only mounted when `ENV=dev-mock`**. Never call them in dev or production.

### Playwright fixtures

`src/stankbot/web/frontend/e2e/fixtures.ts` exposes:

- `mockLogin(user?)` — authenticate Playwright as a mock user.
- `mockBotGuilds(guilds)` — set bot guilds for guild switcher tests.
- `newSession()` — break any active chain, end session, and reload.
- `injectStank(guildId, userId, displayName)` — trigger a stank and assert WS + DOM updates.
- `injectBreak(guildId, userId, displayName)` — trigger a chain break.
- `injectReaction(guildId, messageId, userId)` — inject a reaction bonus.
- `startRandomEvents(interval?)` / `stopRandomEvents()` — drive background state changes.

Use `data-testid` selectors in Svelte components for stable Playwright queries. Prefer fixtures over manual `page.goto` + `page.fill` sequences.

### E2E coverage rule (absolute)

If your change affects a user-facing dashboard flow — board rendering, chain display, player profiles, admin settings, session views, auth state, WebSocket updates, or toast notifications — and there is **no existing E2E test** covering that flow, **you must add one**. No exceptions. The test must exercise the modified route or interaction and assert on either DOM state or WebSocket frame content.

## Architectural invariants

Detailed enforcement lives in auto-invoked skills:

- **`stank-event-sourcing`** — `events` table is source of truth; totals are derived; log is append-only; rebuilds replay, never patch. Triggers when touching code that mutates domain state.
- **`stank-service-purity`** — `services/` is framework-agnostic (no `discord.py`); `cogs/` translates Discord ↔ services; `web/` imports services directly. Triggers when editing those layers.
- **`stank-embed-templates`** — template variables are `{snake_case}` so services pass context dicts directly. Triggers when editing templates / renderers.
- **`stank-ws-protocol`** — frontend `MsgType` enum and backend `MSG_TYPE_*` constants must stay in sync. Triggers when editing WS message type definitions.

## What this project is

**StankBot** is a server-side Python Discord Application that runs the Stank chain game for one or more guilds.

- A long-running Python process built on `discord.py` (Gateway-based) and `FastAPI` (web dashboard).
- Multi-guild from day one; every domain table keyed by `guild_id`.
- Event-sourced (see `stank-event-sourcing`).
- Rendered as Discord rich embeds, per-guild templates authored on the dashboard.
- Single process by default (`python -m stankbot` starts the bot + the dashboard on port 8000); can be split later.

### Core gameplay
Members post messages containing the `:Stank:` emoji/sticker in a designated **altar channel**. Consecutive valid stanks build a **chain**. Any non-stank message in the altar **breaks** the chain. A guild may register multiple altars (`altars` table), each with its own sticker, chain, and optional scoring overrides.

- **SP (Stank Points):** reward currency for stankers.
- **PP (Punishment Points):** sin counter for chainbreakers.
- **Cooldown:** per (user, altar); configurable; default 20 min. Restanking inside cooldown reacts but awards nothing and doesn't advance the chain.

### SP / PP math (defaults; per-altar override on `altars` row)
- Per valid stank: `sp_flat` (10) + (chain position − 1).
- Chain starter (position 1): extra `sp_starter_bonus` (15).
- **Finish bonus** `sp_finish_bonus` (15) — retroactively on chain break, to the most recent stanker **who is not the chainbreaker** (walks back `chain_messages`; if the entire chain is just the breaker, no bonus).
- Reactions award `sp_reaction` (1) to the reactor — only on messages in the live chain, and only the **first** time the pair (message, user, sticker) is recorded in `reaction_awards`.
- Chainbreaker penalty: `pp_break_base` (25) + (broken chain length × `pp_break_per_stank` (2)).

## Where to look first

- **Scoring math & constants:** [src/stankbot/services/scoring_service.py](src/stankbot/services/scoring_service.py).
- **Live chain handling:** [src/stankbot/services/chain_service.py](src/stankbot/services/chain_service.py). The ONLY place chain state transitions happen.
- **Session boundaries:** [src/stankbot/services/session_service.py](src/stankbot/services/session_service.py). Emits `session_start`/`session_end` events — no snapshot tables.
- **Schema:** [src/stankbot/db/models.py](src/stankbot/db/models.py). Authority for all tables.
- **Reaction awards:** [src/stankbot/db/repositories/reaction_awards.py](src/stankbot/db/repositories/reaction_awards.py). Tracks per (message, user) first-reaction-only; chain_id scoping is critical to correctness.
- **Embed rendering:** [src/stankbot/services/board_renderer.py](src/stankbot/services/board_renderer.py) + [template_engine.py](src/stankbot/services/template_engine.py) + [template_store.py](src/stankbot/services/template_store.py) + [embed_builders.py](src/stankbot/services/embed_builders.py).
- **Cogs (Discord surface):** [src/stankbot/cogs/](src/stankbot/cogs/).
- **Dashboard API:** [src/stankbot/web/app.py](src/stankbot/web/app.py) (factory) + [routes/api.py](src/stankbot/web/routes/api.py) + [routes/admin.py](src/stankbot/web/routes/admin.py) + [routes/auth.py](src/stankbot/web/routes/auth.py).
- **WebSocket:** [src/stankbot/web/ws.py](src/stankbot/web/ws.py). Cookie-based auth; broadcast hub for live board updates. The frontend uses msgpack for both WS and HTTP (`apiFetch` negotiates msgpack encoding).
- **Auth flow:** [src/stankbot/web/routes/auth.py](src/stankbot/web/routes/auth.py) + [src/stankbot/cogs/auth_cog.py](src/stankbot/cogs/auth_cog.py). Mock login (`/auth/mock-login`), session cookies, admin check, guild permissions. E2E tests use the `mockLogin(user?)` fixture which also clears the frontend session cache.
- **Frontend API client:** [src/stankbot/web/frontend/src/lib/api.ts](src/stankbot/web/frontend/src/lib/api.ts) — `apiFetch` wrapper with msgpack negotiation, retry, error handling.
- **Frontend stores:** [src/stankbot/web/frontend/src/lib/stores/](src/stankbot/web/frontend/src/lib/stores/) — cross-component state for board, auth, toasts, WS events.
- **Frontend components:** [src/stankbot/web/frontend/src/lib/components/](src/stankbot/web/frontend/src/lib/components/) — reusable UI primitives (`Button`, `Modal`, `Tabs`, `Dropdown`, `StatTile`, `RemovableItem`, `ToastContainer`, `GuildSwitcher`, etc.).
- **WebSocket client:** [src/stankbot/web/frontend/src/lib/ws.ts](src/stankbot/web/frontend/src/lib/ws.ts) — connection lifecycle, msgpack encoding, `MsgType` enum shared with backend.
- **Shared utilities:** [src/stankbot/web/frontend/src/lib/format.ts](src/stankbot/web/frontend/src/lib/format.ts) — `formatNumber()` for M/K suffix display, `formatDuration()` for `XhYm` duration formatting. [src/stankbot/web/frontend/src/lib/api-utils.ts](src/stankbot/web/frontend/src/lib/api-utils.ts) — `toErrorMessage()` for standardized error extraction, `loadWithFallback()` for page load error resilience.

## Reference files

- [pyproject.toml](pyproject.toml) — dependencies, version, tool config.
- [alembic.ini](alembic.ini) + [migrations/](migrations/) — schema migrations.
- [deploy/](deploy/) — systemd unit, Docker setup, watchdog fallback.
- [railway.json](railway.json) — Railway deploy config.
- [README.md](README.md) — user-facing install & usage. Source of truth is the code; README must not drift.
- [src/stankbot/web/frontend/e2e/](src/stankbot/web/frontend/e2e/) — Playwright E2E tests and fixtures.
- [scripts/dev.ps1](scripts/dev.ps1) / [scripts/dev.sh](scripts/dev.sh) — one-command dev startup.
- [scripts/run-e2e.mjs](scripts/run-e2e.mjs) — cross-platform E2E launcher (spawns backend, health-polls, kills on exit).
- `.env.dev-mock` — dev-mock configuration template (mock Discord, mock auth, separate DB). Committed — no secrets.
- `.env.dev` — real Discord credentials for local dev. Not committed.
