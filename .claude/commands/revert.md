---
description: Revert the most recent N commits (default 1). If the reverted head migration needs a downgrade, add one. Then commit and push.
---

Revert and re-ship with rollback support.

## Steps

### 1. Determine what to revert
Run `git log --oneline -5` and ask the user how many commits to revert (default 1).

### 2. Identify the migration(s) being reverted
For each reverted commit, check if it introduced or modified migrations:
```
git show <commit> --name-only --diff-filter=M | grep migrations/versions
```
If any of those revisions have a non-trivial downgrade (i.e. the `downgrade()` body is not just `pass`), a **downgrade migration is needed.

### 3. Draft revert commits
For **each** commit being reverted (oldest first if multiple):
```
git revert --no-commit <hash>
```
Stage only the files that were in that commit.

### 4. Add downgrade migration if needed
For each migration revision identified in step 2:
- Open `migrations/versions/<revision>.py`
- If `downgrade() -> None:` body is just `pass`, write the proper downgrade SQL that restores the old schema
- **Typical patterns:**

  *Table renamed/recreated* (our pattern for admin_users):
  ```python
  def downgrade() -> None:
      conn = op.get_bind()
      conn.exec_driver_sql("DROP TABLE admin_users")
      conn.exec_driver_sql(
          "CREATE TABLE admin_users ("
          "guild_id INTEGER NOT NULL, "
          "user_id INTEGER NOT NULL, "
          "added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
          "PRIMARY KEY (guild_id, user_id), "
          "FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE"
          ")"
      )
      # Existing rows are dropped; recreate from app data if needed.
  ```

  *Column added (nullable, no dflt)*:
  ```python
  def downgrade() -> None:
      with op.batch_alter_table("table_name") as batch:
          batch.drop_column("column_name")
  ```

  *Column added with default*:
  ```python
  def downgrade() -> None:
      with op.batch_alter_table("table_name", copy_from=op.get_bind().dialect.name) as batch:
          batch.drop_column("column_name")
  ```

- Stage the modified migration file.

### 5. Sync README.md
If the revert removes user-visible surface (commands, settings, pages), restore the README to match the pre-feature state. Otherwise skip.

### 6. Commit (no version bump, no push)
```
git commit -m "revert: <short description>"
```
**Do not** bump the version — reverts are internal maintenance.
**Do not** run pre-commit hooks.
**Do not** push — confirm with the user first.

### 7. Confirm and push
Show `git log --oneline -3` and `git diff --stat HEAD~N..HEAD`. Ask user to confirm before pushing.
On confirm: `git push`.

## Guardrails
- Never revert a revert of the revert — linear history only.
- If the working tree is dirty beyond the revert, report and stop.
- Never push without explicit user confirmation.