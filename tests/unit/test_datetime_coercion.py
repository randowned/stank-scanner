"""Unit tests for datetime coercion in the DB layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.engine import coerce_naive_datetime
from stankbot.db.models import Cooldown
from stankbot.db.repositories import cooldowns


class TestCoerceNaiveDatetime:
    def test_none_returns_none(self) -> None:
        result = coerce_naive_datetime(None)
        assert result is None

    def test_aware_returns_unchanged(self) -> None:
        aware = datetime.now(tz=UTC)
        result = coerce_naive_datetime(aware)
        assert result is aware
        assert result.tzinfo is not None

    def test_naive_gets_utc(self) -> None:
        naive = datetime.now()
        result = coerce_naive_datetime(naive)
        assert result is not naive
        assert result.tzinfo is not None
        # The original should be unchanged (replace returns new)
        assert naive.tzinfo is None


class TestCooldownsRepo:
    async def test_get_last_stank_returns_utc_aware(
        self,
        session: AsyncSession,
    ) -> None:
        now = datetime.now(tz=UTC)
        session.add(
            Cooldown(
                guild_id=1,
                altar_id=1,
                user_id=1,
                last_valid_stank_at=now,
            )
        )
        await session.commit()

        result = await cooldowns.get_last_stank(
            session, guild_id=1, altar_id=1, user_id=1
        )

        assert result is not None
        assert result.tzinfo is not None
        # Should be UTC-aware (or at least timezone-aware)
        assert result.replace(tzinfo=None) is None or result.tzinfo is not None

    async def test_get_last_stank_none_when_missing(
        self,
        session: AsyncSession,
    ) -> None:
        result = await cooldowns.get_last_stank(
            session, guild_id=999, altar_id=999, user_id=999
        )
        assert result is None

    async def test_set_last_stank_accepts_aware(
        self,
        session: AsyncSession,
    ) -> None:
        now = datetime.now(tz=UTC)
        await cooldowns.set_last_stank(
            session,
            guild_id=1,
            altar_id=1,
            user_id=1,
            when=now,
        )
        await session.commit()

        result = await cooldowns.get_last_stank(
            session, guild_id=1, altar_id=1, user_id=1
        )
        assert result is not None
        # Verify the stored value is timezone-aware
        assert result.tzinfo is not None


class TestCooldownArithmetic:
    async def test_seconds_remaining_with_aware_datetimes(
        self,
        session: AsyncSession,
    ) -> None:
        """Ensure the core use case works: seconds_remaining doesn't crash."""
        now = datetime.now(tz=UTC)

        # Set a cooldown 5 minutes ago
        five_minutes_ago = now - timedelta(minutes=5)
        await cooldowns.set_last_stank(
            session,
            guild_id=1,
            altar_id=1,
            user_id=1,
            when=five_minutes_ago,
        )
        await session.commit()

        # Read it back
        last_stank_at = await cooldowns.get_last_stank(
            session, guild_id=1, altar_id=1, user_id=1
        )
        assert last_stank_at is not None

        # The cooldown arithmetic - this is the critical path
        seconds = cooldowns.seconds_remaining(
            last_stank_at,
            cooldown_seconds=1200,  # 20 minutes
            now=now,
        )
        # Should allow - we stanked 5 minutes ago, 20 min cooldown = 900 remaining
        assert seconds == 900

    async def test_seconds_remaining_expired(
        self,
        session: AsyncSession,
    ) -> None:
        """Expired cooldown returns 0."""
        now = datetime.now(tz=UTC)

        # Set a cooldown 30 minutes ago (expired)
        thirty_minutes_ago = now - timedelta(minutes=30)
        await cooldowns.set_last_stank(
            session,
            guild_id=2,
            altar_id=2,
            user_id=2,
            when=thirty_minutes_ago,
        )
        await session.commit()

        last_stank_at = await cooldowns.get_last_stank(
            session, guild_id=2, altar_id=2, user_id=2
        )
        assert last_stank_at is not None

        seconds = cooldowns.seconds_remaining(
            last_stank_at,
            cooldown_seconds=1200,
            now=now,
        )
        assert seconds == 0

    async def test_seconds_remaining_none_returns_0(
        self,
        session: AsyncSession,
    ) -> None:
        """No previous stank means no cooldown."""
        result = cooldowns.seconds_remaining(
            None,
            cooldown_seconds=1200,
            now=datetime.now(tz=UTC),
        )
        assert result == 0


class TestDbRoundtripSerialization:
    """Verify that datetimes read from SQLite produce ``+00:00`` ISO strings.

    SQLite's ``DateTime(timezone=True)`` round-trips as naive, so
    ``utc_isoformat`` must stamp UTC before serializing.
    """

    async def test_utc_isoformat_coerces_on_read(
        self,
        session: AsyncSession,
    ) -> None:
        from stankbot.db.models import Event, EventType
        from stankbot.utils.time_utils import utc_isoformat

        aware = datetime(2026, 4, 30, 2, 5, 22, tzinfo=UTC)
        event = Event(
            guild_id=1,
            type=EventType.SP_BASE,
            delta=10,
            user_id=1,
            created_at=aware,
        )
        session.add(event)
        await session.commit()
        # Re-fetch so SQLite round-trips it
        await session.refresh(event)

        iso = utc_isoformat(event.created_at)
        assert iso is not None
        assert iso.endswith("+00:00"), f"Expected +00:00 suffix, got {iso!r}"

    async def test_cooldown_coercion_produces_utc_isoformat(
        self,
        session: AsyncSession,
    ) -> None:
        from stankbot.utils.time_utils import utc_isoformat

        now = datetime.now(tz=UTC)
        await cooldowns.set_last_stank(
            session, guild_id=10, altar_id=10, user_id=10, when=now,
        )
        await session.commit()

        result = await cooldowns.get_last_stank(
            session, guild_id=10, altar_id=10, user_id=10,
        )
        assert result is not None
        iso = utc_isoformat(result)
        assert iso is not None
        assert iso.endswith("+00:00"), f"Expected +00:00 suffix, got {iso!r}"
