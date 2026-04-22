---
name: stank-embed-templates
description: Conventions for stank-bot's per-guild embed templates (board, record, session-start/end, points, cooldown). Trigger when editing src/stankbot/services/template_engine.py, board_renderer.py, default template strings, or dashboard routes that author templates.
---

# stank-bot embed template conventions

Embeds are authored per-guild on the web dashboard and rendered by `template_engine.py` + `board_renderer.py`. Players never see ASCII — everything is a Discord rich embed.

## Rules

1. **Template variables are `{snake_case}`.**
   - They match Python identifiers intentionally so the service layer can pass a context dict directly without key translation.
   - No `{camelCase}`, no `{dashed-names}`, no `{spaces inside braces}`.

2. **Context flows: service → renderer → template.**
   - The service builds a plain dict (`{"chain_length": 7, "top_stanker": "alice", ...}`).
   - The renderer passes that dict to the template engine.
   - The template substitutes `{chain_length}`, `{top_stanker}`, etc.
   - Do not introduce a separate "template context" type that diverges from what services already return.

3. **Templates are per-guild, authored via the dashboard.**
   - Default templates live in code (for fresh guilds) but are copied into the guild's settings on first use.
   - Do not hardcode guild-specific strings in renderers.

4. **Known template slots:** board, record announcement, session-start, session-end, points, cooldown. If you're adding a new slot, add it to the dashboard authoring UI and the renderer at the same time.

## Red flags

- A new template variable named in camelCase or with a format that doesn't match a Python identifier.
- A renderer that transforms keys (e.g. `chain_length` → `chainLength`) before passing to the template.
- ASCII-only output where an embed was expected.
- Guild-specific copy hardcoded in `board_renderer.py` instead of living in the template.

## Key files

- `src/stankbot/services/board_renderer.py`
- `src/stankbot/services/template_engine.py`
- Dashboard template authoring: `src/stankbot/web/routes/` (template-related routes).
