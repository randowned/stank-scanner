"""SQLAlchemy models — authoritative schema for StankBot.

Design invariants (enforced by code review, see AGENTS.md):
    * Every domain row is keyed by ``guild_id`` — multi-guild from day one.
    * The ``events`` table is the source of truth. ``records`` and the
      ``player_totals`` view are caches regenerable from the event log.
    * Session boundaries are stored as events (``session_start``,
      ``session_end``), not as rows in a ``sessions`` table. Any row that
      references a session uses the ``id`` of the corresponding
      ``session_start`` event as its ``session_id``.
    * Discord snowflakes are stored as BigInteger (64-bit).
    * JSON blobs use the portable ``JSON`` type so SQLite and Postgres
      both work with the same schema.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# SQLite only supports autoincrement on INTEGER PRIMARY KEY (rowid). For PK
# columns that still need to be 64-bit on Postgres, use this variant so the
# right type is emitted per-dialect.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums (stored as strings for portability across SQLite/Postgres)
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    # Scoring
    SP_BASE = "sp_base"
    SP_POSITION_BONUS = "sp_position_bonus"
    SP_STARTER_BONUS = "sp_starter_bonus"
    SP_FINISH_BONUS = "sp_finish_bonus"
    SP_REACTION = "sp_reaction"
    SP_TEAM_PLAYER = "sp_team_player"
    PP_BREAK = "pp_break"
    # Lifecycle (zero-delta marker events)
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    CHAIN_START = "chain_start"
    CHAIN_BREAK = "chain_break"
    # Achievements
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"


class SessionEndReason(StrEnum):
    AUTO = "auto"  # scheduled session rollover
    MANUAL = "manual"  # /stank-admin new-session
    BOARD_RESET = "board_reset"  # /stank-admin reset


class ChannelPurpose(StrEnum):
    ANNOUNCEMENTS = "announcements"


class RecordScope(StrEnum):
    SESSION = "session"
    ALLTIME = "alltime"


# ---------------------------------------------------------------------------
# Guild-level
# ---------------------------------------------------------------------------


class Guild(Base):
    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GuildSetting(Base):
    """Per-guild key/value settings. ``value_json`` carries the typed value.

    Settings service reads/writes these with validation; templates, scoring
    overrides, reset hours, feature toggles all live here.
    """

    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdminRole(Base):
    """Roles granted admin privileges. Additive on top of Manage Guild."""

    __tablename__ = "admin_roles"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminUser(Base):
    """Individual users granted global admin privileges.

    A ``guild_id`` of 0 marks a global entry (the actual guild_id column
    is kept for DB backward compat but ignored in permission checks).
    Additive on top of ``AdminRole`` + ``Manage Guild`` + bot owner.
    """

    __tablename__ = "admin_users"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=0)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChannelBinding(Base):
    """Command + announcement channels. Altar channels live in ``altars``."""

    __tablename__ = "channel_bindings"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(32), primary_key=True)  # ChannelPurpose


class Altar(Base):
    """The guild's single altar — a (channel, sticker) binding.

    One altar per guild; multi-altar was removed in favour of keeping
    configuration trivial. ``altar_id`` remains on dependent tables as a
    stable foreign key for historical rows.
    """

    __tablename__ = "altars"
    __table_args__ = (
        UniqueConstraint("guild_id", name="uq_altar_guild"),
        Index("ix_altars_guild_enabled", "guild_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Optional exact-sticker snowflake (kept for thumbnail rendering only).
    # Matching happens by name.
    sticker_id: Mapped[int | None] = mapped_column(BigInteger)
    # Exact-match (case-insensitive) against incoming sticker names.
    sticker_name_pattern: Mapped[str] = mapped_column(
        String(120), nullable=False, default="stank", server_default="stank"
    )
    # Reaction that awards the SP_REACTION bonus. Either a custom emoji id
    # OR a unicode emoji character stored in ``reaction_emoji_name``.
    reaction_emoji_id: Mapped[int | None] = mapped_column(BigInteger)
    reaction_emoji_name: Mapped[str | None] = mapped_column(String(120))
    reaction_emoji_animated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Per-altar scoring overrides. NULL => fall back to guild-level setting.
    sp_flat_override: Mapped[int | None] = mapped_column(Integer)
    sp_position_bonus_override: Mapped[int | None] = mapped_column(Integer)
    sp_starter_bonus_override: Mapped[int | None] = mapped_column(Integer)
    sp_finish_bonus_override: Mapped[int | None] = mapped_column(Integer)
    sp_reaction_override: Mapped[int | None] = mapped_column(Integer)
    pp_break_base_override: Mapped[int | None] = mapped_column(Integer)
    pp_break_per_stank_override: Mapped[int | None] = mapped_column(Integer)
    cooldown_seconds_override: Mapped[int | None] = mapped_column(Integer)

    custom_event_key: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


class Player(Base):
    __tablename__ = "players"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    discord_avatar: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Chains
# ---------------------------------------------------------------------------


class Chain(Base):
    __tablename__ = "chains"
    __table_args__ = (
        Index("ix_chains_guild_altar", "guild_id", "altar_id"),
        Index("ix_chains_guild_broken_at", "guild_id", "broken_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    altar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("altars.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    broken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    starter_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    broken_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    final_length: Mapped[int | None] = mapped_column(Integer)
    final_unique: Mapped[int | None] = mapped_column(Integer)


class ChainMessage(Base):
    __tablename__ = "chain_messages"
    __table_args__ = (
        Index("ix_chain_messages_chain", "chain_id", "position"),
        Index("ix_chain_messages_user_chain", "user_id", "chain_id"),
    )

    chain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chains.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Event log (source of truth)
# ---------------------------------------------------------------------------


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_guild_user", "guild_id", "user_id"),
        Index("ix_events_guild_session", "guild_id", "session_id"),
        Index("ix_events_guild_chain", "guild_id", "chain_id"),
        Index("ix_events_guild_type_created", "guild_id", "type", "created_at"),
        Index("ix_events_custom_key", "guild_id", "custom_event_key"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    altar_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("altars.id", ondelete="SET NULL")
    )
    session_id: Mapped[int | None] = mapped_column(BigInteger)  # id of the session_start event
    chain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chains.id", ondelete="SET NULL")
    )
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(40), nullable=False)  # EventType
    delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    custom_event_key: Mapped[str | None] = mapped_column(String(64))
    payload_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReactionAward(Base):
    """Anti-cheat ledger: one row per (message, user, sticker).

    Insertion is idempotent; the row is NEVER deleted, even if the user
    removes the reaction from Discord. Re-adding cannot trigger a second
    SP award because the row (and thus the enforcing PK) already exists.
    """

    __tablename__ = "reaction_awards"

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sticker_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    chain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chains.id", ondelete="SET NULL")
    )
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Caches (regenerable from events)
# ---------------------------------------------------------------------------


class Record(Base):
    """Best-chain cache. scope=session resets per session; scope=alltime never."""

    __tablename__ = "records"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    altar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("altars.id", ondelete="CASCADE"), primary_key=True
    )
    scope: Mapped[str] = mapped_column(String(16), primary_key=True)  # RecordScope
    chain_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chains.id", ondelete="SET NULL")
    )
    session_id: Mapped[int | None] = mapped_column(BigInteger)


class Cooldown(Base):
    """Per (guild, altar, user) cooldown tracker."""

    __tablename__ = "cooldowns"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    altar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("altars.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_valid_stank_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PlayerTotal(Base):
    """Materialized-view-style cache refreshed by ScoringService on each event.

    Regenerable: ``SUM(delta) FROM events GROUP BY guild_id, user_id, type-category``.
    """

    __tablename__ = "player_totals"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=0)
    # session_id=0 means "all-time" aggregate; non-zero is the session_start event id
    earned_sp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    punishments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stanks_in_session: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reactions_in_session: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Player Chain Totals
# ---------------------------------------------------------------------------


class PlayerChainTotal(Base):
    """Per-chain, per-user stank/reaction counts.

    Regenerable: COUNT(SP_BASE), COUNT(SP_REACTION) FROM events
    GROUP BY guild_id, user_id, chain_id.
    """

    __tablename__ = "player_chain_totals"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stanks_in_chain: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reactions_in_chain: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


class Achievement(Base):
    """Catalog of achievements. Rules are encoded in ``rule_json`` + a
    Python evaluator class resolved at runtime. ``is_global`` means the
    achievement ships with the bot; per-guild bespoke achievements are
    a future enhancement.
    """

    __tablename__ = "achievements"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(200))
    rule_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlayerBadge(Base):
    __tablename__ = "player_badges"
    __table_args__ = (
        UniqueConstraint(
            "guild_id", "user_id", "achievement_key", name="uq_player_badge_unique"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    achievement_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("achievements.key", ondelete="CASCADE"), nullable=False
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    chain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chains.id", ondelete="SET NULL")
    )
    session_id: Mapped[int | None] = mapped_column(BigInteger)


# ---------------------------------------------------------------------------
# Media (Maphra — platform-agnostic media analytics)
# ---------------------------------------------------------------------------


class MediaItem(Base):
    """Metadata for a tracked media item (YouTube video, Spotify track, etc.).

    Scoped per-guild. Unique per (guild_id, media_type, external_id).
    Metrics themselves live in :class:`MetricCache` (latest) and
    :class:`MetricSnapshot` (time-series).
    """

    __tablename__ = "media_items"
    __table_args__ = (
        UniqueConstraint("guild_id", "media_type", "external_id", name="uq_media_item_unique"),
        UniqueConstraint("guild_id", "slug", name="uq_media_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255))
    channel_id: Mapped[str | None] = mapped_column(String(128))
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    added_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metrics_last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MetricCache(Base):
    """Latest metric values — one row per (media_item, metric_key).

    Upserted on every refresh for fast list-page renders without scanning
    the full time-series table.
    """

    __tablename__ = "metric_cache"

    media_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True
    )
    metric_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MetricSnapshot(Base):
    """Time-series metric snapshots — one row per refresh per metric.

    Use for historical charts. Query with:
        SELECT fetched_at, value FROM metric_snapshots
        WHERE media_item_id = ? AND metric_key = ? AND fetched_at >= ?
        ORDER BY fetched_at
    """

    __tablename__ = "metric_snapshots"
    __table_args__ = (
        Index("ix_metric_snapshots_item_key_time", "media_item_id", "metric_key", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Every admin mutation (slash + web) writes a row here for accountability."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_guild_created", "guild_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
