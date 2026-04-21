---
description: Version-bump, sync README, commit, and push the current working-tree changes.
---

Ship the current working-tree changes following the stank-bot workflow rules.

## Steps

### 1. Inspect the change
Run `git status` and `git diff` (staged and unstaged). Summarize what actually changed in one line.

### 2. Decide the version bump
Version source of truth: the `version` field in `pyproject.toml`.

- **Patch (`Z`)** — bug fixes, internal tweaks, no user-visible behavior change.
- **Minor (`Y`)** — new user-visible features, new slash commands, new settings, dashboard additions, non-breaking behavior changes.
- **Major (`X`)** — breaking DB schema changes (beyond alembic autogenerate), removed commands, scoring-math changes that invalidate historical data.

### 3. Sync README.md
If the change touches user-visible surface (commands, settings, scoring defaults, game rules, dashboard pages, install/run steps), update `README.md` to match. Scan only sections the change affects.

If purely internal (refactor, tests, CI, internal rename), state so explicitly and skip the README edit.

### 4. Update version
Edit `pyproject.toml` so `version = "X.Y.Z"` matches the bump you picked.

### 5. Commit
- Message format: `vX.Y.Z - {short context}`
  - `v2.1.0 - feat: add altar multi-sticker support`
  - `v2.0.1 - fix: cooldown leaking across altars`
- **Never** add a `Co-Authored-By` or any AI-authored trailer.
- Stage only the files that belong to this change.

### 6. Push
- `git push` to the current branch.
- **Do not** open a pull request. This project ships directly from the branch.
- **Do not** switch, create, rebase, or merge branches unless the user explicitly asked.

## Guardrails
- If the working tree is clean, report that and exit — no empty commits.
- If push is rejected, report and ask before force-push or rebase.
