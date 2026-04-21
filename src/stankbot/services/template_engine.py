"""Embed template engine — ``{snake_case}`` substitution.

Templates are stored per-guild in ``guild_settings`` as structured dicts
(title / description / color / fields / footer / thumbnail / timestamp).
This module takes a template dict and a variables dict, and returns a
ready-to-send ``discord.Embed``.

Convention: all variables are ``snake_case`` — the engine rejects any
``{CamelCase}`` / ``{kebab-case}`` token to catch user typos in the web
editor before they hit Discord.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import discord

# {identifier} where identifier starts with a-z or underscore, contains only
# a-z/0-9/underscore. Uppercase letters or dashes in the identifier are a
# validation error — see `validate_template_variables`.
_VAR_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_\-]*)\}")
_VALID_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class TemplateError(ValueError):
    """Raised for malformed templates (bad variable names, unknown keys)."""


@dataclass(slots=True)
class RenderContext:
    """Values available for substitution. Keys must all be snake_case.

    Values are coerced to ``str`` at render time via ``format()``; pass
    numbers as ints and ``pre_format`` helpers (e.g. ``humanize_duration``)
    before populating the context.
    """

    variables: dict[str, Any]


def validate_template_variables(text: str) -> list[str]:
    """Return the list of ``{var}`` tokens in ``text`` or raise ``TemplateError``
    if any token is not valid snake_case.

    Called by the web editor on save so bad tokens surface with a clear
    error before being committed to ``guild_settings``.
    """
    found: list[str] = []
    for match in _VAR_PATTERN.finditer(text):
        ident = match.group(1)
        if not _VALID_IDENT.match(ident):
            raise TemplateError(
                f"Template variable {{{ident}}} is not snake_case. "
                f"Use lowercase letters, digits, and underscores only."
            )
        found.append(ident)
    return found


def substitute(text: str, ctx: RenderContext) -> str:
    """Replace ``{var}`` tokens in ``text`` with values from ``ctx``.

    Unknown variables are left as-is (rendered literally) — this keeps the
    editor forgiving. Use ``validate_template_variables`` at save time to
    enforce naming, and ``strict_substitute`` below when a missing variable
    must surface as an error (e.g. the live-preview endpoint).
    """
    validate_template_variables(text)

    def _replace(match: re.Match[str]) -> str:
        ident = match.group(1)
        if ident in ctx.variables:
            return str(ctx.variables[ident])
        return match.group(0)

    return _VAR_PATTERN.sub(_replace, text)


def strict_substitute(text: str, ctx: RenderContext) -> str:
    """Like ``substitute`` but raises ``TemplateError`` on unknown variables."""
    validate_template_variables(text)

    def _replace(match: re.Match[str]) -> str:
        ident = match.group(1)
        if ident not in ctx.variables:
            raise TemplateError(f"Unknown template variable: {{{ident}}}")
        return str(ctx.variables[ident])

    return _VAR_PATTERN.sub(_replace, text)


def _parse_color(value: str | int | None) -> discord.Color | None:
    if value is None:
        return None
    if isinstance(value, int):
        return discord.Color(value)
    s = value.strip()
    if s.startswith("#"):
        s = s[1:]
    return discord.Color(int(s, 16))


def render_embed(
    template: dict[str, Any],
    ctx: RenderContext,
    *,
    strict: bool = False,
) -> discord.Embed:
    """Build a ``discord.Embed`` from a template dict + context.

    Template shape (all keys optional except that at least one of
    title/description/fields should be set or Discord rejects the embed):

        {
          "title": str,
          "description": str,
          "color": "#RRGGBB" | int,
          "thumbnail": url-str,
          "image": url-str,
          "author": {"name": str, "icon": url-str},
          "footer": str,
          "timestamp": "auto" | ISO8601 | None,
          "fields": [
            {"name": str, "value": str, "inline": bool},
            ...
          ],
        }
    """
    sub = strict_substitute if strict else substitute

    embed = discord.Embed()
    if title := template.get("title"):
        embed.title = sub(str(title), ctx)
    if description := template.get("description"):
        embed.description = sub(str(description), ctx)
    raw_color = template.get("color")
    if isinstance(raw_color, str) and "{" in raw_color:
        raw_color = sub(raw_color, ctx)
    if color := _parse_color(raw_color):
        embed.color = color
    if thumbnail := template.get("thumbnail"):
        embed.set_thumbnail(url=sub(str(thumbnail), ctx))
    if image := template.get("image"):
        embed.set_image(url=sub(str(image), ctx))
    if (author := template.get("author")) and isinstance(author, dict):
        name = author.get("name")
        icon = author.get("icon")
        url = author.get("url")
        embed.set_author(
            name=sub(str(name), ctx) if name else "",
            icon_url=sub(str(icon), ctx) if icon else None,
            url=sub(str(url), ctx) if url else None,
        )
    if footer := template.get("footer"):
        embed.set_footer(text=sub(str(footer), ctx))
    ts = template.get("timestamp")
    if ts == "auto":
        from datetime import UTC, datetime

        embed.timestamp = datetime.now(tz=UTC)
    # ISO-string timestamps are intentionally ignored for now — only "auto"
    # is supported; a future enhancement can parse explicit ISO dates.
    for field in template.get("fields", []) or []:
        if not isinstance(field, dict):
            continue
        embed.add_field(
            name=sub(str(field.get("name", "\u200b")), ctx),
            value=sub(str(field.get("value", "\u200b")), ctx),
            inline=bool(field.get("inline", False)),
        )
    return embed
