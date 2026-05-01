"""Default embed templates — code-managed, not user-editable.

Each template is a plain dict consumed by ``template_engine.render_embed``.
Variables are ``{snake_case}`` and documented in the plan's "Template
variable vocabulary" section.

Clickable surfaces in Discord embeds:
    * ``author.url`` — makes the author *name* clickable (we set it to
      the guild board URL so "StankBot" links back to the dashboard).
    * Channel mentions ``<#id>`` inside *description* or *field values*
      render as clickable channel pills. Footers render plain text only,
      so the altar channel is mentioned in the description instead.
"""

from __future__ import annotations

from typing import Any

BOARD_EMBED: dict[str, Any] = {
    "color": "#a47cff",
    "title": "{stank_emoji} Stank Board {stank_emoji}",
    "description": (
        "\u26d3\ufe0f **Current chain:** {current} stanks \u00b7 {current_unique} unique"
        " \u00b7 in {altar_channel_mention}"
    ),
    "thumbnail": "{altar_sticker_url}",
    "author": {"name": "StankBot", "url": "{board_url}"},
    "fields": [
        {
            "name": "\U0001f4ca Records",
            "value": (
                "\U0001f3cb\ufe0f All-time   {alltime_record} / {alltime_record_unique} unique\n"
                "\U0001f517 Session   {record} / {record_unique} unique\n"
                "\u23f3 Next reset   {next_reset_in}"
            ),
            "inline": False,
        },
        {
            "name": "\U0001f465 Titles",
            "value": (
                "\U0001f3c3\u200d\u27a1\ufe0f Chain starter   {chain_starter_name} \u00b7 **{chain_starter_sp} SP**\n"
                "\U0001f480 The Chainbreaker   {chainbreaker_name} \u00b7 **-{chainbreaker_punishments} SP**"
            ),
            "inline": False,
        },
        {
            "name": "\U0001f3c6 Top {stank_rows_limit}",
            "value": "{stank_rankings_table}",
            "inline": False,
        },
    ],
}


# Merged record template: session + all-time in one embed. The service
# passes marker variables ({session_marker}, {alltime_marker}) set to
# "**" (bold) when that scope was broken, or "" when it wasn't.
# {record_title} / {record_description} / color vary based on which
# record(s) were broken (see _record_record_vars in chain listener).
RECORD_EMBED: dict[str, Any] = {
    "color": "{record_color}",
    "title": "{record_title}",
    "description": "{record_description} \u00b7 in {altar_channel_mention}",
    "thumbnail": "{altar_sticker_url}",
    "author": {"name": "StankBot", "url": "{board_url}"},
    "fields": [
        {
            "name": "\U0001f4ca Records",
            "value": (
                "\U0001f451 All-time   {alltime_marker}{alltime_record} / {alltime_record_unique} unique{alltime_marker}\n"
                "\U0001f517 This session   {session_marker}{record} / {record_unique} unique{session_marker}"
            ),
            "inline": False,
        },
        {
            "name": "\U0001f3c3\u200d\u27a1\ufe0f Chain starter",
            "value": "{chain_starter_name} \u00b7 **{chain_starter_sp} SP**",
            "inline": False,
        },
    ],
}


# Fired whenever an active chain breaks. Attached alongside RECORD_EMBED
# when a record was also broken on the same message.
CHAIN_BREAK_EMBED: dict[str, Any] = {
    "color": "#ef4444",
    "title": "\U0001f4a5 Chain broken",
    "description": (
        "{breaker_name} broke a **{broken_length}-stank** chain "
        "({broken_unique} unique) in {altar_channel_mention}. "
        "**-{pp_awarded} SP**."
    ),
    "thumbnail": "{altar_sticker_url}",
    "author": {"name": "StankBot", "url": "{board_url}"},
    "fields": [
        {
            "name": "\U0001f3c3\u200d\u27a1\ufe0f Chain starter",
            "value": "{chain_starter_name} \u00b7 **{chain_starter_sp} SP**",
            "inline": True,
        },
        {
            "name": "\U0001f3c1 Finish bonus",
            "value": "{finish_recipient_name} \u00b7 **+{finish_bonus_sp} SP**",
            "inline": True,
        },
    ],
}


# Single unified session-rollover template. Replaces SESSION_START +
# SESSION_END — the scheduler fires one post covering the close of the
# previous session and the open of the next, plus all-time stats.
NEW_SESSION_EMBED: dict[str, Any] = {
    "color": "#10b981",
    "title": "\u2728 New session \u2014 #{new_session_number}",
    "description": (
        "Session **#{ended_session_number}** closed in {altar_channel_mention}. "
        "{chain_continuity_summary}"
    ),
    "author": {"name": "StankBot", "url": "{board_url}"},
    "fields": [
        {
            "name": "\U0001f3c5 Last session",
            "value": (
                "\U0001f517 Stanks {prev_session_record} / {prev_session_record_unique} unique\n"
                "\U0001f3c6 Leader \u00b7 {session_top_player} \u00b7 **{session_top_sp} SP**\n"
                "\U0001f480 Breaker \u00b7 {session_top_breaker} \u00b7 **-{session_top_breaker_pp} SP**"
            ),
            "inline": False,
        },
        {"name": "\u200b", "value": "\u200b", "inline": False},
        {"name": "\u23f3 Next reset", "value": "{next_reset_in}", "inline": False},
        {"name": "\u200b", "value": "\u200b", "inline": False},
        {
            "name": "\U0001f451 All-time",
            "value": (
                "\U0001f517 Stanks {alltime_record} / {alltime_record_unique} unique\n"
                "\u2728 Leader \u00b7 {alltime_top_sp_player} \u00b7 **{alltime_top_sp} SP**\n"
                "\U0001f480 Breaker \u00b7 {alltime_top_pp_player} \u00b7 **-{alltime_top_pp} SP**"
            ),
            "inline": False,
        },
    ],
}


COOLDOWN_EMBED: dict[str, Any] = {
    "color": "#f59e0b",
    "title": "\u23f1\ufe0f Cooldown",
    "description": (
        "{target_display_name} must wait **{cooldown_remaining}** to stank again "
        "in {altar_channel_mention} (cooldown: {cooldown_total})."
    ),
    "author": {"name": "StankBot", "url": "{board_url}"},
}


POINTS_EMBED: dict[str, Any] = {
    "color": "#a47cff",
    "author": {"name": "{target_display_name}", "icon": "{target_avatar_url}"},
    "description": "Rank **#{rank}** \u00b7 {net_sp_sign}**{net_sp}** net",
    "fields": [
        {"name": "\u2728 SP earned", "value": "{earned_sp}", "inline": True},
        {"name": "\U0001f480 SP Lost", "value": "{punishments}", "inline": True},
        {
            "name": "\u26d3\ufe0f Chains started",
            "value": "{chains_started}",
            "inline": True,
        },
        {
            "name": "\U0001f4a5 Chains broken",
            "value": "{chains_broken}",
            "inline": True,
        },
        {"name": "\U0001f3c5 Badges", "value": "{badge_list}", "inline": False},
    ],
    "footer": "Last stank: {last_stank_rel}",
}


YOUTUBE_MEDIA_EMBED: dict[str, Any] = {
    "color": "#ff0000",
    "title": "{title}",
    "url": "{url}",
    "description": "by **{channel_name}**",
    "image": "{image_url}",
    "fields": [
        {
            "name": "\U0001f441\ufe0f Views",
            "value": "{view_count}\n{view_count_delta}".strip(),
            "inline": True,
        },
        {
            "name": "\U0001f44d Likes",
            "value": "{like_count}\n{like_count_delta}".strip(),
            "inline": True,
        },
        {
            "name": "\U0001f4ac Comments",
            "value": "{comment_count}\n{comment_count_delta}".strip(),
            "inline": True,
        },
        {"name": "\U0001f4c5 Published", "value": "{published_at}", "inline": True},
        {"name": "\u23f1 Duration", "value": "{duration}", "inline": True},
    ],
    "footer": "\U0001f3ac YouTube \u00b7 {slug} \u00b7 Updated {last_fetched_at}",
}


SPOTIFY_MEDIA_EMBED: dict[str, Any] = {
    "color": "#1db954",
    "title": "{title}",
    "url": "{url}",
    "description": "by **{channel_name}**",
    "image": "{image_url}",
    "fields": [
        {
            "name": "\U0001f525 Popularity",
            "value": "{popularity}\n{popularity_delta}".strip(),
            "inline": True,
        },
        {"name": "\U0001f4c5 Released", "value": "{published_at}", "inline": True},
        {"name": "\U0001f3b5 Type", "value": "{spotify_type}", "inline": True},
    ],
    "footer": "\U0001f3b5 Spotify \u00b7 {slug} \u00b7 Updated {last_fetched_at}",
}


ALL_DEFAULTS: dict[str, dict[str, Any]] = {
    "board_embed": BOARD_EMBED,
    "record_embed": RECORD_EMBED,
    "chain_break_embed": CHAIN_BREAK_EMBED,
    "new_session_embed": NEW_SESSION_EMBED,
    "cooldown_embed": COOLDOWN_EMBED,
    "points_embed": POINTS_EMBED,
    "youtube_media_embed": YOUTUBE_MEDIA_EMBED,
    "spotify_media_embed": SPOTIFY_MEDIA_EMBED,
}
