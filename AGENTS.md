# AGENTS.md

Operational guide for AI agents (Claude Code, etc.) working in this repository. Keep this file current: update it when workflow rules or architecture change.

Procedures live in `.claude/commands/` (user-triggered) and `.claude/skills/` (auto-invoked). This file is the map — not the procedures themselves.

## Workflow rules

These rules override any default behavior. Follow them strictly.

### Branches
- **Only work on `main`, or on a branch the user explicitly names.** Never create, switch, rebase, or merge branches on your own. No worktrees — edit the files in place.
- **No pull requests.** Never run `gh pr create` or open a PR. The project ships directly from branches.
- **Save changes directly to files and stop.** Do not stage, do not commit. The user previews changes in another editor via its git integration, so unstaged edits are exactly what they want to see.

### Commits
- **Never commit unless the user explicitly asks.** After finishing a change, stop and wait.
- Shipping is handled by `/commit-and-push` (version bump + README sync + commit + push). Docs-only sync is `/update-docs`.
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

### Environments

| Mode | Env file | Discord | Auth | Purpose |
|------|----------|---------|------|---------|
| `dev` | `.env.dev` | Mocked (`mock_discord=true`) | Mocked (`mock_auth=true`) | Local development, manual testing, E2E |
| `preprod` | `.env.preprod` | Real token | Real OAuth | Staging / local with real Discord |
| `production` | System env / Railway | Real token | Real OAuth | Live deploy |

- `.env.local` has been renamed to `.env.preprod`. Do not re-create `.env.local`.
- `.env.dev` is committed as a template (no secrets) and uses a separate SQLite DB (`stankbot_dev.db`).
- Never enable `mock_discord` or `mock_auth` outside `ENV=dev`. The code gates these with `if config.env == "dev"`; respect that invariant.

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

### E2E test execution

- **For agent verification during development:** `cd src/stankbot/web/frontend && npm run test:e2e:dev` (Vite dev server, fastest iteration).
- **For commit-and-push readiness:** `cd src/stankbot/web/frontend && npm run test:e2e` (production static build, closest to real deploy).

Both require the backend running in `ENV=dev`. Use the one-command startup scripts:
- Windows: `.\scripts\dev.ps1`
- macOS/Linux: `./scripts/dev.sh`

### Mock event injection

When verifying in `ENV=dev`, use the mock API to drive state changes without Discord:

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

These endpoints are **only mounted when `ENV=dev`**. Never call them in preprod or production.

### Playwright fixtures

`src/stankbot/web/frontend/e2e/fixtures.ts` exposes:

- `mockLogin(user?)` — authenticate Playwright as a mock user.
- `injectStank(guildId, userId, displayName)` — trigger a stank and assert WS + DOM updates.
- `injectBreak(guildId, userId, displayName)` — trigger a chain break.
- `startRandomEvents(interval?)` / `stopRandomEvents()` — drive background state changes.

Use `data-testid` selectors in Svelte components for stable Playwright queries. Prefer fixtures over manual `page.goto` + `page.fill` sequences.

### E2E coverage rule (absolute)

If your change affects a user-facing dashboard flow — board rendering, chain display, player profiles, admin settings, session views, auth state, WebSocket updates, or toast notifications — and there is **no existing E2E test** covering that flow, **you must add one**. No exceptions. The test must exercise the modified route or interaction and assert on either DOM state or WebSocket frame content.

## Architectural invariants

Detailed enforcement lives in auto-invoked skills:

- **`stank-event-sourcing`** — `events` table is source of truth; totals are derived; log is append-only; rebuilds replay, never patch. Triggers when touching code that mutates domain state.
- **`stank-service-purity`** — `services/` is framework-agnostic (no `discord.py`); `cogs/` translates Discord ↔ services; `web/` imports services directly. Triggers when editing those layers.
- **`stank-embed-templates`** — template variables are `{snake_case}` so services pass context dicts directly. Triggers when editing templates / renderers.

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
- **Embed rendering:** [src/stankbot/services/board_renderer.py](src/stankbot/services/board_renderer.py) + [template_engine.py](src/stankbot/services/template_engine.py).
- **Cogs (Discord surface):** [src/stankbot/cogs/](src/stankbot/cogs/).
- **Dashboard API:** [src/stankbot/web/v2_app.py](src/stankbot/web/v2_app.py) + [v2_admin.py](src/stankbot/web/v2_admin.py).

## Reference files

- [pyproject.toml](pyproject.toml) — dependencies, version, tool config.
- [alembic.ini](alembic.ini) + [migrations/](migrations/) — schema migrations.
- [deploy/](deploy/) — systemd unit, Docker setup, watchdog fallback.
- [railway.json](railway.json) — Railway deploy config.
- [README.md](README.md) — user-facing install & usage. Source of truth is the code; README must not drift.
- [src/stankbot/web/frontend/e2e/](src/stankbot/web/frontend/e2e/) — Playwright E2E tests and fixtures.
- [scripts/dev.ps1](scripts/dev.ps1) / [scripts/dev.sh](scripts/dev.sh) — one-command dev startup.
- `.env.dev` — dev mode configuration template (mock Discord, mock auth, separate DB).
