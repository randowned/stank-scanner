---
name: stank-event-sourcing
description: Enforces stank-bot's event-sourcing invariants when writing code that mutates domain state. Trigger when adding/editing any code path that changes player totals, chain state, sessions, records, or achievements — i.e. anything in src/stankbot/services/* or repositories that writes to the DB. Also trigger when writing rebuild/backfill scripts that touch totals.
---

# stank-bot event sourcing invariants

The `events` table is the **source of truth** for all domain state. Totals, session summaries, records, and achievements are derived from event queries. Snapshot tables (`records`, `player_totals`, etc.) are caches — regenerable from the event log at any time.

## Rules when mutating domain state

1. **Every mutation appends an `events` row.** No exceptions. If your code path changes player totals, chain state, session state, or any user-visible score, there must be a corresponding event insert.

2. **Admin actions also append an `audit_log` row.** Anything that an operator triggers manually (not a player action from Discord) needs audit trail in addition to the event.

3. **The event log is append-only.** Do not UPDATE or DELETE rows in `events`. If a prior event was wrong, emit a correcting event — don't rewrite history.

4. **Rebuilds rewrite the log, never patch totals in place.** When regenerating snapshot tables (`records`, `player_totals`), replay the event log into fresh caches. Do not `UPDATE player_totals SET sp = ...` as a fix — it will drift from the events.

5. **Snapshot tables are disposable.** If `records` and the derived-from-events result disagree, the events win. Rebuild the snapshot.

## Where the rules live

- Schema: `src/stankbot/db/models.py` — `events`, `audit_log`, snapshot tables.
- Canonical write paths: `src/stankbot/services/chain_service.py`, `src/stankbot/services/scoring_service.py`, `src/stankbot/services/session_service.py`.

## Red flags to catch in review

- A service method that writes to a snapshot table but not to `events`.
- An admin endpoint that mutates state with no `audit_log` insert.
- A "fix" migration that patches totals directly instead of emitting a correcting event + rebuilding.
- A test that asserts on snapshot tables without also asserting the event log.
