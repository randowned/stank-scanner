# AGENTS.md

Operational guide for AI agents (Claude Code, etc.) working in this repository. Keep this file current: update it when workflow rules or architecture change.

## Workflow rules

These rules override any default behavior. Follow them strictly.

### Branches
- **Only work on `main`, or on a branch the user explicitly names.** Never create, switch, rebase, or merge branches on your own. No worktrees — edit the files in place.
- **No pull requests.** Never run `gh pr create` or open a PR. The project ships directly from branches.
- **Save changes directly to files and stop.** Do not stage, do not commit. The user previews changes in another editor via its git integration, so unstaged edits are exactly what they want to see.

### Commits
- **Never commit unless the user explicitly asks.** After finishing a change, stop and wait. The user will say "commit it" (or equivalent) when ready.
- **No `Co-Authored-By` trailer.** Never add AI co-author trailers to commit messages or PR bodies. (Also enforced via `~/.claude/CLAUDE.md`.)
- **Commit message format:** `vX.Y.Z - {short context}`
  - Example: `v3.6.0 - feat: chainbreaker no longer gets finish bonus`
  - Example: `v3.5.1 - fix: board message not sent after reset`
- **Version bumps are managed by the agent.** Decide the bump based on the change:
  - **Patch (`Z`):** bug fixes, internal tweaks, no behavior change for users.
  - **Minor (`Y`):** new user-visible features, new commands, new settings, non-breaking behavioral changes.
  - **Major (`X`):** breaking changes to saved data shape, settings schema, or user-facing command contracts.
- **Update the version in [StankBot.plugin.js](StankBot.plugin.js) header (`@version` line, around line 5) as part of the commit.** The plugin version and the commit message version must match.
- **Update [README.md](README.md) before every commit.** Review the staged/unstaged changes and sync any user-facing sections that have drifted (features, commands, settings, SP/PP math, defaults, templates). Treat README maintenance the same as the version bump: a required step in the commit flow, not an optional polish. If the change is purely internal and the README genuinely needs no edit, say so explicitly when asking to commit.
- Current version lives at the top of `StankBot.plugin.js` — check it before drafting a bump.

### Subagents
Use subagents (the `Agent` tool with `Explore`, `Plan`, or `general-purpose`) when the work genuinely benefits from delegation. The plugin is a single ~2000-line file, so most small edits don't need a subagent — but the ones below do.

**Use a subagent when:**
- Tracing a concept across many locations (e.g. "how does the cooldown interact with the sync/replay path") where you'd otherwise read hundreds of lines into the main context.
- Designing a non-trivial change that touches both the live handler and the replay path — spawn a `Plan` agent to validate the approach before editing.
- Running independent investigations in parallel (e.g. one agent maps SP math, another maps persistence keys) so the main context stays clean.
- Using a tool whose output is noisy or large (broad greps, multi-file reads) that would otherwise bloat context for little signal.

**Don't use a subagent for:**
- Edits to a known function at a known line.
- One-shot greps or reads you can do directly with `Grep`/`Read`.
- "Find this string" tasks — use `Grep` directly.

When delegating, brief the agent self-contained: state the goal, name the files/symbols already known, and cap the response length. Never ask a subagent to commit, push, or open PRs — that stays with the main session under the rules above.

**Track whether subagents are actually helping.** After a delegation, notice: did the subagent save time and context, or did it just add a round-trip that you ended up re-doing? If subagents are consistently slowing things down on this repo — its small size often means direct `Grep`/`Read` wins — tune the heuristics above downward, or stop using them entirely. Update this section of [AGENTS.md](AGENTS.md) to reflect what's actually working. Removing the subagent guidance altogether is a valid outcome; don't preserve it out of inertia.

### Other defaults
- Stay inside the repo; don't touch external systems without being asked.
- Prefer editing existing code to adding new files. This project is a single-file plugin by design.

## What this project is

**StankBot** is a single-file BetterDiscord plugin (`StankBot.plugin.js`) that manages a Discord community's `#altar` channel for the Maphra server. It is installed by dropping the file into BetterDiscord's plugins folder; there is no build step, no npm install, no test suite.

### Core gameplay
Members post messages containing the `:Stank:` emoji in the altar channel. Consecutive valid stanks build a **chain**. Any non-stank message posted into the altar **breaks** the chain.

- **SP (Stank Points)** — reward currency. Awarded to stankers.
- **PP (Punishment Points)** — sin counter. Awarded to chainbreakers.
- **Cooldown:** each user must wait `RESTANK_COOLDOWN_MS` (20 min) between valid stanks. Re-stanking inside the cooldown reacts to the message but awards nothing and does not advance the chain.

### SP / PP math (see class constants at top of plugin)
- Per valid stank: `SP_FLAT` (10) + (chain position − 1).
- Chain starter (position 1) gets an extra `SP_STARTER_BONUS` (15).
- **Finish bonus** `SP_FINISH_BONUS` (15) — retroactively awarded when the chain breaks, to the most recent stanker **who is not the chainbreaker** (walks back through chain contributors; if the entire chain is just the breaker, no bonus is awarded).
- Reactions award `SP_REACTION` (1) to the reactor, but only on messages tracked in the current chain.
- Chainbreaker penalty: `SP_BREAK_BASE` (25) + (broken chain length × `SP_BREAK_PER_STANK` (2)).

### Key state (all lives on `this`)
- `currentChain` — count of valid stanks in the live chain.
- `chainUniqueUsers` — array of unique author IDs in the live chain.
- `currentChainMessageIds` — Set of message IDs that count toward the live chain (used to scope reaction awards).
- `chainContributors` — ordered `[{id, username}]` of every valid stank in the live chain. Used to find the finish-bonus recipient on break.
- `chainStarterId` — author of position 1.
- `lastStankTimestamps` — `{userId: ts}` for cooldown enforcement.
- `stankboard` — the persistent leaderboard: `{userId: {username, points, punishments, ...}}`.
- `recordChain` / `recordChainUnique` — current session records.
- `alltimeRecord` / `alltimeRecordUnique` — all-time records.
- `lastBrokenChainLength` — length of the most recent broken chain.
- `seenMsgIds` / `processedReactions` — dedupe caches (Discord dispatches MESSAGE_CREATE and reaction events multiple times).

### Persistence
Uses `BdApi.Data.save/load("StankBot", key)`. Settings are stored under the `settings` key; other state (stankboard, chainStarterId, lastPunishedMessageId, etc.) is stored as siblings. The bot also writes a BetterDiscord `config.json` (see `syncConfigFromDisk`).

### Sync / replay
On startup or manual sync, the bot fetches recent altar messages, groups them into alternating `CHAIN` and `GAP` runs, and replays XP/punishments for messages newer than the last-processed IDs. The live handler (`processAltarMessage`) and the replay path (`processAllAltarMessages`) must stay behaviorally aligned — any change to award logic in one needs the matching change in the other.

### Templates
Four customizable templates (set in plugin settings) with `{variable}` substitution:
- `scoreTemplate` — score command / board message body (`{stankBoard}`, `{record}`, `{current}`, `{nextResetIn}`, …)
- `recordTemplate` — announced when a new chain record is set
- `bioTemplate` — user bio sync
- `boardTemplate` — full rankings table body (`{stankRankingsTable}`, `{chainStarterName}`, `{chainbreakerName}`, …)

The word "Chainbreaker" in `boardTemplate` refers to the all-time PP leader (most cumulative punishments), *not* the specific person who broke the latest chain.

### Resets
Chain/session records reset on a schedule defined by `RESET_TARGETS` (hours: 7, 15, 23). `RESET_WARNING_MINS` (30, 5) controls pre-reset warning announcements. A board auto-update interval refreshes the board message every `boardUpdateIntervalSeconds`.

### Where to look first
- Class constants and construction: top of [StankBot.plugin.js](StankBot.plugin.js) (lines 1–100).
- Live message handler: `processAltarMessage` — grep for it.
- Historical replay: `processAllAltarMessages` — grep for it.
- Board rendering: `applyCommonReplacements` and its callers.
- Settings panel: `getSettingsPanel`.

### Reference files
- [StankBot.plugin.js](StankBot.plugin.js) — the entire plugin.
- [README.md](README.md) — user-facing description (may drift from code; source of truth is the plugin).
