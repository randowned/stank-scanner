"""SessionService — session lifecycle, event-sourced.

Session boundaries are events in the log:
    * ``session_start`` (id X) — X becomes the session_id for all rows
      created until the next ``session_end``.
    * ``session_end`` — closes the window; a new ``session_start`` is
      emitted immediately after unless this was a full reset.

Because sessions are derived from events, **no ``sessions`` table exists**.
Any past session can be reconstructed by filtering the event stream
between two matching start/end markers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import EventType, SessionEndReason
from stankbot.db.repositories import cooldowns as cooldowns_repo
from stankbot.db.repositories import events as events_repo
from stankbot.services import achievements as achievements_svc
from stankbot.services.chain_service import SessionIdProvider

if TYPE_CHECKING:
    from stankbot.db.models import Event


@dataclass(slots=True)
class SessionService(SessionIdProvider):
    """Session lifecycle + "what is the current session_id?" lookups.

    Implements ``SessionIdProvider`` so ``ChainService`` can ask for the
    current session id without knowing about SessionService directly.
    """

    session: AsyncSession

    async def current(self, guild_id: int) -> int | None:
        """Return the id of the currently-alive ``session_start`` event,
        or ``None`` if no session is open.

        "Alive" = the most recent ``session_start`` has no matching
        ``session_end`` yet. Callers that need an id to tag new events
        should prefer ``ensure_started`` so a dead guild auto-opens.
        """
        latest = await events_repo.latest_session_start_id(self.session, guild_id)
        if latest is None:
            return None
        if not await self._session_is_alive(guild_id, latest):
            return None
        return latest

    async def ensure_started(
        self, guild_id: int, *, when: datetime | None = None
    ) -> int:
        """If no session is currently open, emit ``session_start`` and
        return the new session id. Otherwise return the existing id.
        """
        current = await self.current(guild_id)
        if current is not None:
            return current
        event = await events_repo.append(
            self.session,
            guild_id=guild_id,
            type=EventType.SESSION_START,
            reason="session started",
            created_at=when,
        )
        return event.id

    async def end_session(
        self,
        guild_id: int,
        *,
        reason: SessionEndReason = SessionEndReason.AUTO,
        open_new: bool = True,
        when: datetime | None = None,
    ) -> tuple[int | None, int | None]:
        """Close the current session; optionally open a new one.

        Returns ``(ended_session_id, new_session_id)`` — either half can
        be ``None`` (e.g. when called on a guild with no prior session,
        or when ``open_new=False``).
        """
        now = when or datetime.now(tz=UTC)
        ended_id = await self.current(guild_id)
        if ended_id is not None:
            await events_repo.append(
                self.session,
                guild_id=guild_id,
                type=EventType.SESSION_END,
                session_id=ended_id,
                reason=str(reason),
                created_at=now,
            )
            # Cooldowns reset at the shift boundary so a player can be the
            # last stank of one shift and the first of the next.
            await cooldowns_repo.clear_for_guild(self.session, guild_id=guild_id)
            participants = await events_repo.session_participants(
                self.session, guild_id, ended_id
            )
            if participants:
                await achievements_svc.evaluate_session_close(
                    self.session,
                    guild_id=guild_id,
                    user_ids=participants,
                    session_id=ended_id,
                )
        new_id: int | None = None
        if open_new:
            new_event = await events_repo.append(
                self.session,
                guild_id=guild_id,
                type=EventType.SESSION_START,
                reason=f"follows {reason}",
                created_at=now,
            )
            new_id = new_event.id
        return ended_id, new_id

    async def _session_is_alive(self, guild_id: int, session_id: int) -> bool:
        """True if no ``session_end`` event exists for this session id."""
        from sqlalchemy import select

        from stankbot.db.models import Event

        stmt = (
            select(Event.id)
            .where(
                Event.guild_id == guild_id,
                Event.session_id == session_id,
                Event.type == EventType.SESSION_END,
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is None

    async def session_events(
        self, guild_id: int, session_id: int
    ) -> list[Event]:
        """All events in a given session, ordered oldest-first. Used by
        ``HistoryService`` to build session summaries on demand — no
        snapshot table needed.
        """
        return list(await events_repo.events_in_session(self.session, guild_id, session_id))
