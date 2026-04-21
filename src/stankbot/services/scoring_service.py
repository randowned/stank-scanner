"""Scoring rules for SP/PP.

Kept framework-agnostic so the cog layer, the CLI rebuild, and the web
dashboard can all run the same computation. No Discord or DB objects flow
through this module — just plain ints and dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass

# Defaults — seeded into guild_settings on install.
DEFAULT_SP_FLAT: int = 10
DEFAULT_SP_POSITION_BONUS: int = 1  # added as (position - 1) * this
DEFAULT_SP_STARTER_BONUS: int = 15
DEFAULT_SP_FINISH_BONUS: int = 15
DEFAULT_SP_REACTION: int = 1
DEFAULT_PP_BREAK_BASE: int = 25
DEFAULT_PP_BREAK_PER_STANK: int = 2
DEFAULT_RESTANK_COOLDOWN_SECONDS: int = 20 * 60  # 20 minutes


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """Effective scoring values for a single altar.

    Built by ``SettingsService.effective_scoring(altar)`` — merges
    per-altar overrides on top of guild-level settings on top of
    defaults. Pass this into the pure functions below.
    """

    sp_flat: int = DEFAULT_SP_FLAT
    sp_position_bonus: int = DEFAULT_SP_POSITION_BONUS
    sp_starter_bonus: int = DEFAULT_SP_STARTER_BONUS
    sp_finish_bonus: int = DEFAULT_SP_FINISH_BONUS
    sp_reaction: int = DEFAULT_SP_REACTION
    pp_break_base: int = DEFAULT_PP_BREAK_BASE
    pp_break_per_stank: int = DEFAULT_PP_BREAK_PER_STANK
    cooldown_seconds: int = DEFAULT_RESTANK_COOLDOWN_SECONDS


def stank_sp(position: int, config: ScoringConfig) -> int:
    """SP awarded for a valid stank at ``position`` (1-indexed) in the chain.

    ``sp_flat + (position - 1) * sp_position_bonus``, with the
    starter (position 1) additionally getting ``sp_starter_bonus``.
    """
    if position < 1:
        raise ValueError(f"position must be >= 1, got {position}")
    sp = config.sp_flat + (position - 1) * config.sp_position_bonus
    if position == 1:
        sp += config.sp_starter_bonus
    return sp


def break_pp(broken_length: int, config: ScoringConfig) -> int:
    """PP penalty for breaking a chain of ``broken_length`` stanks.

    ``pp_break_base + length * pp_break_per_stank``.
    """
    if broken_length < 0:
        raise ValueError(f"broken_length must be >= 0, got {broken_length}")
    return config.pp_break_base + broken_length * config.pp_break_per_stank


def finish_bonus_recipient(
    contributors: list[int], breaker_user_id: int | None
) -> int | None:
    """Walk the chain backwards; return the most recent contributor who
    is NOT the breaker. Returns ``None`` if no such contributor exists
    (e.g. the chain contained only the breaker, or the chain was empty).

    If the chain contains only the breaker, no finish bonus is awarded.
    """
    for user_id in reversed(contributors):
        if user_id != breaker_user_id:
            return user_id
    return None
