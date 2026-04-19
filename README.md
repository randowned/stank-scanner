![](static/Stank.gif)

# StankBot

**StankBot** is a custom [BetterDiscord](https://betterdiscord.app/) plugin built for tracking community sticker chains in the [Maphra Discord Server](https://discord.gg/maphra).

It listens to the `#altar` channel for "Stank" sticker chains, awards Stank Points and Punishment Points, and dynamically updates your Server Bio and Nickname when the current or record chain lengths are changed.

## The Game

Players cooperate to build the longest chain of "Stank" stickers in `#altar`. The chain breaks when anyone posts a non-sticker message.

Rankings are based on **net Stank Points** (earned SP minus punishment points).

| Action | Points |
|---|---|
| Chain starter (first stank) | +10 + 15 SP bonus = **+25 SP**, become **Slayer** |
| Each subsequent valid stank (position N) | +10 + (N−1) SP |
| Last poster when chain breaks (excluding the chainbreaker) | +15 SP retroactive finish bonus |
| Stank emoji reaction on ongoing-chain sticker | +1 SP (once per user per sticker) |
| Break the chain | −(25 + chain length × 2) PP |

> **Cooldown:** The same user cannot stank again for **10 minutes** within a chain. Cooldowns reset when the chain breaks.

> **The Chainbreaker:** The leaderboard footer highlights the player with the highest all-time punishment points.

## Commands

| Command | Description |
|---|---|
| `!stank-board` | The leaderboard (ranked by net SP) |
| `!stank-points` | Your Stank Points and rank |
| `!stank-points <rank>` | Look up a player by rank |
| `!stank-help` | Help message with rules |

### Admin Commands (bot owner only)

| Command | Description |
|---|---|
| `!stank-record-test` | Preview record announcement |
| `!stank-new-session` | End the current session (wipes SP/PP and session records) without breaking the chain |
| `!stank-board-reset` | Full wipe: scoreboard, records, **and** the ongoing chain |
| `!stank-board-reload` | Full wipe and replay from channel history |

## Features

- **Net Score Ranking**: Players ranked by `earned SP - punishment points`. Breakdown shown in `!stank-points`.
- **Chain Tracking**: Tracks the longest unbroken chain of Stank stickers. Displays total stanks and unique stanker count.

## v3 Highlights

- **Automatic session schedule**: Sessions end automatically at **7:00**, **15:00**, and **23:00** local time. Session end wipes SP/PP and session records but **keeps the ongoing chain alive** — chain length, unique stankers, chain starter, and per-user cooldowns all carry over. Session records restart at the continuing chain's current length. Use `!stank-board-reset` if you need to wipe the chain too.
- **Announcement support**: Session-end events are announced through configured announcement channels.
- **Countdown display**: `{nextResetIn}` is available in board templates to show time until the next session.
- **Persistent scheduling**: Session timers survive plugin reloads and continue logging schedules.
- **Improved reset handling**: Manual `!stank-board-reset` and bot board reloads still do a full wipe (chain included) for when you really need to start fresh.
- **Position-based XP**: Each stank earns more SP as the chain grows — position N earns `10 + (N−1)` SP.
- **Retroactive Finish Bonus**: When the chain breaks, +15 SP goes to the most recent valid stanker who is **not** the chainbreaker. The chain is walked backwards to skip any trailing stanks by the breaker themselves; if the whole chain was the breaker, no bonus is awarded.
- **Per-user Cooldown**: 5-minute cooldown per user prevents spam-stanking; violations get a callout with the time remaining.
- **The Chainbreaker**: Board footer shows the player with the highest all-time punishment points.
- **History Scraping**: Reconstructs chain state from channel history on startup, including cooldown tracking.
- **Automated Sessions**: Sessions end three times daily at **7:00**, **15:00**, and **23:00** local time. The scoreboard resets; the chain keeps going.
- **Session Announcements**: New-session announcements are posted to configured announcement channels.
- **Next Session Countdown**: Default board templates include `{nextResetIn}` so the next session-start time is visible.
- **Dynamic Updates**: Auto-updates your Server Bio and Nickname (e.g. `Username (10/32)`) with current scores.
- **Command Channels**: Configurable allowlist of channel IDs for command auto-replies. DMs always work.
- **Announcement Channels**: Separate allowlist for record-broken announcements. `!stank-help` works in both command and announcement channels.
- **Logging**: Persistent log file (`StankBot.log`) in the plugins folder with ISO timestamps and session separators. Auto-reset scheduling and trigger events are logged for easier confirmation.
- **Customization**: Configurable templates for Bio, Nickname, board layout, and record announcements.

## Installation

1. Download and install [BetterDiscord](https://betterdiscord.app/).
2. Open Discord → **User Settings** → **BetterDiscord** → **Plugins**.
3. Click **"Open Plugins Folder"** to open `%appdata%\BetterDiscord\plugins`.
4. Drop `StankBot.plugin.js` into the folder.
5. Enable **StankBot** in the Plugins menu.

## Important

> **Self-Bot Warning:** Auto-replying to other users relies on your user account sending API requests without manual input, which goes against Discord's TOS regarding self-bots. Use at your own risk.

---

*Developed for the Maphra Discord Community.*
