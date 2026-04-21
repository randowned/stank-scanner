"""Achievements — pure functions over the event log.

An ``Achievement`` rule is a small callable that, given an ``AsyncSession``
and a ``(guild_id, user_id)`` pair, returns ``True`` if the player has
earned the badge. Evaluation is idempotent — a second run when the badge
is already recorded is a no-op courtesy of the ``player_badges`` unique
constraint.

The catalog is code-bound by key. Rows in the ``achievements`` table are
a lightweight registry the dashboard can render; the actual rule logic
lives in ``_RULES`` below. Adding a new achievement = add an entry in
``_RULES`` + an Alembic data-migration row.

Event triggers:
    * Per-stank / per-break events call ``evaluate_for_user`` after the
      scoring write — cheap O(badges) checks, most are early-returned by
      a single COUNT or EXISTS query.
    * Session-end calls ``evaluate_session_close`` to settle achievements
      that only resolve once a session boundary exists.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from stankbot.db.models import (
    Chain,
    ChainMessage,
    Event,
    EventType,
    PlayerBadge,
)
from stankbot.db.repositories import events as events_repo

log = logging.getLogger(__name__)


Rule = Callable[[AsyncSession, int, int], Awaitable[bool]]


@dataclass(slots=True, frozen=True)
class AchievementDef:
    key: str
    name: str
    description: str
    icon: str
    rule: Rule
    # Only evaluated on session close (needs session boundary state).
    session_close_only: bool = False


# --- individual rules -----------------------------------------------------


async def _first_stank(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    stmt = (
        select(Event.id)
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
            Event.type == EventType.SP_BASE,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _chain_starter(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    stmt = (
        select(Event.id)
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
            Event.type == EventType.CHAIN_START,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _finisher(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    stmt = (
        select(Event.id)
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
            Event.type == EventType.SP_FINISH_BONUS,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _centurion(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    # User has posted in at least one chain whose final_length >= 100
    # (still-alive chains with >=100 current messages also qualify).
    count = func.count(ChainMessage.message_id)
    stmt = (
        select(Chain.id)
        .join(ChainMessage, ChainMessage.chain_id == Chain.id)
        .where(Chain.guild_id == guild_id, ChainMessage.user_id == user_id)
        .group_by(Chain.id)
        .having(count >= 100)
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def _chainbreaker_dubious(
    session: AsyncSession, guild_id: int, user_id: int
) -> bool:
    stmt = (
        select(Chain.id)
        .where(
            Chain.guild_id == guild_id,
            Chain.broken_by_user_id == user_id,
            Chain.final_length >= 50,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _comeback_kid(
    session: AsyncSession, guild_id: int, user_id: int
) -> bool:
    sp, pp = await events_repo.sp_pp_totals(session, guild_id, user_id)
    if sp - pp <= 0:
        return False
    # Must have been in the red at some point. Reconstruct by walking
    # events chronologically and tracking the running net.
    stmt = (
        select(Event.type, Event.delta)
        .where(
            Event.guild_id == guild_id,
            Event.user_id == user_id,
        )
        .order_by(Event.id.asc())
    )
    running = 0
    ever_negative = False
    _sp_types = {
        EventType.SP_BASE.value,
        EventType.SP_POSITION_BONUS.value,
        EventType.SP_STARTER_BONUS.value,
        EventType.SP_FINISH_BONUS.value,
        EventType.SP_REACTION.value,
    }
    async for row in await session.stream(stmt):
        t, delta = row
        if t in _sp_types:
            running += int(delta or 0)
        elif t == EventType.PP_BREAK.value:
            running -= int(delta or 0)
        if running < 0:
            ever_negative = True
    return ever_negative


async def _perfect_session(
    session: AsyncSession, guild_id: int, user_id: int
) -> bool:
    # At session close: user had at least one SP event this session and no
    # PP_BREAK events. "This session" = the most recently ended session.
    stmt = (
        select(Event.session_id)
        .where(
            Event.guild_id == guild_id,
            Event.type == EventType.SESSION_END,
        )
        .order_by(Event.id.desc())
        .limit(1)
    )
    last_session_id = (await session.execute(stmt)).scalar_one_or_none()
    if last_session_id is None:
        return False
    sp, pp = await events_repo.sp_pp_totals(
        session, guild_id, user_id, session_id=last_session_id
    )
    return sp > 0 and pp == 0


async def _streaker(
    session: AsyncSession, guild_id: int, user_id: int
) -> bool:
    # User stanked in >= 3 consecutive session_ids (ordered chronologically).
    session_ids = await events_repo.session_event_ids(session, guild_id)
    if len(session_ids) < 3:
        return False
    run = 0
    for sid in session_ids:
        sp, _pp = await events_repo.sp_pp_totals(
            session, guild_id, user_id, session_id=sid
        )
        if sp > 0:
            run += 1
            if run >= 3:
                return True
        else:
            run = 0
    return False


# --- catalog --------------------------------------------------------------


_RULES: tuple[AchievementDef, ...] = (
    AchievementDef(
        key="first_stank",
        name="First Stank",
        description="Dropped your very first stank.",
        icon="✨",
        rule=_first_stank,
    ),
    AchievementDef(
        key="chain_starter",
        name="Chain Starter",
        description="Started a chain.",
        icon="🏃‍➡️",
        rule=_chain_starter,
    ),
    AchievementDef(
        key="centurion",
        name="Centurion",
        description="Posted in a chain that reached 100 stanks.",
        icon="💯",
        rule=_centurion,
    ),
    AchievementDef(
        key="finisher",
        name="Finisher",
        description="Earned the finish bonus on a chain break.",
        icon="🏁",
        rule=_finisher,
    ),
    AchievementDef(
        key="comeback_kid",
        name="Comeback Kid",
        description="Climbed from negative net SP back to positive.",
        icon="📈",
        rule=_comeback_kid,
    ),
    AchievementDef(
        key="perfect_session",
        name="Perfect Session",
        description="Finished a session with SP earned and no breaks.",
        icon="🧼",
        rule=_perfect_session,
        session_close_only=True,
    ),
    AchievementDef(
        key="streaker",
        name="Streaker",
        description="Stanked in three consecutive sessions.",
        icon="⚡",
        rule=_streaker,
        session_close_only=True,
    ),
    AchievementDef(
        key="chainbreaker",
        name="Chainbreaker",
        description="Broke a chain of 50+ stanks. Dubious honor.",
        icon="💀",
        rule=_chainbreaker_dubious,
    ),
)


def catalog_rows() -> list[dict[str, Any]]:
    """Registry data inserted by the data-migration."""
    return [
        {
            "key": a.key,
            "name": a.name,
            "description": a.description,
            "icon": a.icon,
            "rule_json": {"impl": "code", "key": a.key},
            "is_global": True,
        }
        for a in _RULES
    ]


# --- evaluator ------------------------------------------------------------


async def _already_unlocked(
    session: AsyncSession, guild_id: int, user_id: int, key: str
) -> bool:
    stmt = (
        select(PlayerBadge.id)
        .where(
            PlayerBadge.guild_id == guild_id,
            PlayerBadge.user_id == user_id,
            PlayerBadge.achievement_key == key,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _unlock(
    session: AsyncSession,
    *,
    guild_id: int,
    user_id: int,
    achievement: AchievementDef,
    session_id: int | None,
    chain_id: int | None,
) -> bool:
    """Insert the badge + emit ``achievement_unlocked`` event. Returns
    True if newly unlocked, False if the row already existed.
    """
    badge = PlayerBadge(
        guild_id=guild_id,
        user_id=user_id,
        achievement_key=achievement.key,
        chain_id=chain_id,
        session_id=session_id,
    )
    session.add(badge)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False
    await events_repo.append(
        session,
        guild_id=guild_id,
        type=EventType.ACHIEVEMENT_UNLOCKED,
        user_id=user_id,
        session_id=session_id,
        chain_id=chain_id,
        reason=achievement.key,
        payload={"key": achievement.key, "name": achievement.name},
    )
    return True


async def evaluate_for_user(
    session: AsyncSession,
    *,
    guild_id: int,
    user_id: int,
    session_id: int | None = None,
    chain_id: int | None = None,
) -> list[str]:
    """Evaluate all non-session-close rules for ``user_id``. Returns the
    list of newly-unlocked achievement keys.
    """
    unlocked: list[str] = []
    for achievement in _RULES:
        if achievement.session_close_only:
            continue
        if await _already_unlocked(session, guild_id, user_id, achievement.key):
            continue
        try:
            if not await achievement.rule(session, guild_id, user_id):
                continue
        except Exception:  # noqa: BLE001
            log.exception(
                "achievement rule %s failed for guild=%d user=%d",
                achievement.key,
                guild_id,
                user_id,
            )
            continue
        if await _unlock(
            session,
            guild_id=guild_id,
            user_id=user_id,
            achievement=achievement,
            session_id=session_id,
            chain_id=chain_id,
        ):
            unlocked.append(achievement.key)
    return unlocked


async def evaluate_session_close(
    session: AsyncSession, *, guild_id: int, user_ids: list[int], session_id: int
) -> dict[int, list[str]]:
    """Evaluate the session-close-only rules for each participating user."""
    result: dict[int, list[str]] = {}
    for uid in user_ids:
        user_unlocks: list[str] = []
        for achievement in _RULES:
            if not achievement.session_close_only:
                continue
            if await _already_unlocked(session, guild_id, uid, achievement.key):
                continue
            try:
                if not await achievement.rule(session, guild_id, uid):
                    continue
            except Exception:  # noqa: BLE001
                log.exception(
                    "session-close rule %s failed user=%d", achievement.key, uid
                )
                continue
            if await _unlock(
                session,
                guild_id=guild_id,
                user_id=uid,
                achievement=achievement,
                session_id=session_id,
                chain_id=None,
            ):
                user_unlocks.append(achievement.key)
        if user_unlocks:
            result[uid] = user_unlocks
    return result


async def badges_for(
    session: AsyncSession, guild_id: int, user_id: int
) -> list[str]:
    """Return the keys of achievements this user has unlocked."""
    stmt = select(PlayerBadge.achievement_key).where(
        PlayerBadge.guild_id == guild_id,
        PlayerBadge.user_id == user_id,
    )
    return list((await session.execute(stmt)).scalars().all())


def definition(key: str) -> AchievementDef | None:
    for a in _RULES:
        if a.key == key:
            return a
    return None
