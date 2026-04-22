---
description: Sync README.md (and AGENTS.md if workflow/architecture changed) against the current working tree. Docs-only — no staging, no commit.
---

Docs-only sync. Useful when docs drifted but no release is being cut yet.

## Steps

### 1. See what changed
Run `git status` and `git diff`. Note which changes touch user-visible surface.

### 2. Update README.md
Scan for drift in sections the change affects. User-visible surface:
- Slash commands and their arguments.
- Settings / config knobs and their defaults.
- Scoring defaults and game rules.
- Dashboard pages and routes.
- Install / run / deploy steps.

Update only drifted sections. Do not rewrite unrelated prose.

### 3. Update AGENTS.md if applicable
`AGENTS.md` is the operational guide for AI agents. Update it when:
- Workflow rules changed (branching, commit format, version-bump criteria).
- Architectural invariants changed (service-layer rules, event sourcing, embed rendering path).
- The "Where to look first" map became stale.

If neither changed meaningfully, leave it alone.

### 4. Stop
Save edits and stop. Do **not** stage, commit, bump version, or push. Those belong to `/commit-and-push`.
