---
name: stank-service-purity
description: Enforces stank-bot's layer boundaries — services framework-agnostic, cogs handle Discord, web imports services directly. Trigger when editing any file under src/stankbot/services/, src/stankbot/cogs/, or src/stankbot/web/, or when creating new modules in those layers.
---

# stank-bot layer boundaries

The codebase has three layers with strict import rules. Violating them pulls Discord types into places they don't belong and duplicates business logic.

## Rules

1. **`src/stankbot/services/` is framework-agnostic.**
   - No `import discord` or `from discord...` anywhere in `services/`.
   - Services take plain data (ids, strings, dicts, dataclasses) and return plain data plus events.
   - No direct references to `discord.Message`, `discord.Member`, `discord.Guild`, etc.

2. **`src/stankbot/cogs/` is the only place `discord.py` types cross in.**
   - Cogs translate Discord events → service calls.
   - Cogs translate service outputs → embeds for Discord.
   - Business logic does not live in cogs; they are a translation layer.

3. **`src/stankbot/web/` (FastAPI) imports services and repos directly.**
   - No duplicated business logic in web routes.
   - If the dashboard needs scoring or chain behavior, it calls the same service the cog calls.

## Red flags

- A `from discord` import in `src/stankbot/services/`.
- A cog with SQL queries, scoring math, or multi-step state machines inline.
- A web route that re-implements logic already in a service (copy-pasted SP/PP math, chain checks, etc.).
- A new "helper" that takes a `discord.Message` in `services/`.

## Fix pattern

If a service needs Discord context, the cog should extract the primitive data (user id, guild id, channel id, content, timestamp) and pass those. The service returns a result object; the cog renders the embed.
