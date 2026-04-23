"""CLI: ``python -m stankbot.rebuild --guild-id X``.

Starts a minimal bot session (login → ready → rebuild → shutdown). Useful
when the bot isn't running or an admin wants to trigger a rebuild from a
shell. Same destructive semantics as the slash command; no confirmation
prompt — the caller is on the server console.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging

from stankbot.bot import StankBot
from stankbot.config import load_config
from stankbot.logging import setup_logging
from stankbot.services import rebuild_service

log = logging.getLogger("stankbot.rebuild")


async def _run(guild_id: int) -> None:
    config = load_config()
    bot = StankBot(config)

    ready = asyncio.Event()

    @bot.event
    async def on_ready() -> None:  # noqa: F811 - discord.py convention
        ready.set()

    async def progress(msg: str) -> None:
        log.info(msg)

    task = asyncio.create_task(bot.start(config.discord_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=30)
        report = await rebuild_service.rebuild(
            bot, guild_id, progress=progress
        )
        log.info(
            "rebuild done: altars=%d messages=%d valid=%d breaks=%d reactions=%d",
            report.altars_scanned,
            report.messages_scanned,
            report.valid_stanks,
            report.chain_breaks,
            report.reactions_awarded,
        )
    finally:
        await bot.close()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m stankbot.rebuild",
        description="Wipe and replay altar channel history for one guild.",
    )
    parser.add_argument(
        "--guild-id", type=int, required=True, help="Target guild id."
    )
    args = parser.parse_args()

    setup_logging(level="INFO")
    asyncio.run(_run(args.guild_id))


if __name__ == "__main__":
    main()
