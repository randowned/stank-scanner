---
name: stank-embed-templates
description: Conventions for stank-bot's per-guild embed templates (board, record, session-start/end, points, cooldown). Trigger when editing src/stankbot/services/template_engine.py, board_renderer.py, template_store.py, embed_builders.py, default template strings, or dashboard routes that author templates.
---

# stank-bot embed template conventions

Embeds are authored per-guild on the web dashboard and rendered by `template_engine.py` + `board_renderer.py`. Players never see ASCII — everything is a Discord rich embed.

## Rules

1. **Template variables are `{snake_case}`.**
   - They match Python identifiers intentionally so the service layer can pass a context dict directly without key translation.
   - No `{camelCase}`, no `{dashed-names}`, no `{spaces inside braces}`.

2. **Context flows: service → embed_builders → template_engine → Discord.**
   - The service builds a plain dict (`{"chain_length": 7, "top_stanker": "alice", ...}`).
   - `embed_builders.py` centralises context-dict construction for bot-posted embeds (records, chain-breaks, session rollovers, cooldown notices).
   - The template engine loads the guild's template from `template_store.py`, then substitutes `{chain_length}`, `{top_stanker}`, etc.
   - Do not introduce a separate "template context" type that diverges from what services already return.

3. **Templates are per-guild, authored via the dashboard.**
   - Default templates live in `default_templates.py` (for fresh guilds) but are copied into the guild's `guild_settings` rows on first use.
   - `template_store.py` handles load/save/validate against the DB.
   - Do not hardcode guild-specific strings in renderers.

4. **Known template slots:** board, record announcement, session-start, session-end, points, cooldown, plus per-provider media embeds (`youtube_media_embed`, `spotify_media_embed` — keys defined in `settings_service.Keys` and built in `embed_builders.build_media_embed`). If you're adding a new slot, add it to `default_templates.ALL_DEFAULTS`, the dashboard authoring UI, and the renderer at the same time.

5. **Media embed token compatibility:** the canonical name token is `{name}`; `{slug}` is preserved as a legacy alias resolving to the same value (some user-customized templates predate the v2.39.0 rename). Both are supplied by `build_media_embed`; do not drop the alias without a migration.

## Red flags

- A new template variable named in camelCase or with a format that doesn't match a Python identifier.
- A renderer that transforms keys (e.g. `chain_length` → `chainLength`) before passing to the template.
- ASCII-only output where an embed was expected.
- Guild-specific copy hardcoded in `board_renderer.py` instead of living in the template.

## Key files

- `src/stankbot/services/board_renderer.py`
- `src/stankbot/services/template_engine.py`
- `src/stankbot/services/template_store.py` — per-guild DB storage (load/save/validate via `guild_settings` table).
- `src/stankbot/services/embed_builders.py` — centralised context-dict construction for bot-posted embeds (records, chain-breaks, session rollovers, cooldown notices).
- `src/stankbot/services/default_templates.py` — built-in defaults (`ALL_DEFAULTS` dict).
- Dashboard template authoring: `src/stankbot/web/routes/admin.py` (template endpoints).
