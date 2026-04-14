![](static/Stank.gif)

# StankBot

**StankBot** is a custom [BetterDiscord](https://betterdiscord.app/) plugin built for tracking community sticker chains in the [Maphra Discord Server](https://discord.gg/maphra).

It listens to the `#maphra-worship` channel for "Stank" sticker chains, awards Stank Points and Punishment Points, and dynamically updates your Server Bio and Nickname when the current or record chain lengths are changed.

## 🎮 The Game

Players cooperate to build the longest chain of "Stank" stickers in `#worship`. Each **unique user** can contribute once per chain. The chain breaks when anyone posts a non-sticker message.

| Action | Points |
|---|---|
| Start a new chain (1st sticker after break) | +100 SP, become **slayer** |
| First-ever sticker contribution (lifetime) | +50 SP bonus |
| Valid unique chain contribution | +25 SP |
| Stank emoji reaction on a sticker | +5 SP |
| Break the chain | +3× chain length punishment, become **goat** |
| Chat during a broken chain | +1× chain length punishment |
| Break chain then start the next one | +50 flat punishment (cheating!) |

## ⚙️ Commands

| Command | Description |
|---|---|
| `!stank-board` | The leaderboard |
| `!stank-points` | Your Stank and Punishment points |
| `!stank-help` | Help message with rules |

### Admin Commands (bot owner only)

| Command | Description |
|---|---|
| `!stank-record-test` | Preview record announcement |
| `!stank-cheater-test` | Preview cheater caught message |
| `!stank-board-reset` | Reset all board data |
| `!stank-board-reload` | Reset and reload from channel history |

## 🌟 Features

- **Chain Tracking**: Tracks the longest unbroken chain of Stank stickers by unique users.
- **XP & Punishment System**: Awards and punishes players based on their contributions and chain-breaking behavior.
- **Anti-Cheat**: Detects and punishes users who break a chain then immediately start the next one.
- **History Scraping**: Reconstructs chain state from channel history on startup.
- **Dynamic Updates**: Auto-updates your Server Bio and Nickname (e.g. `Username (10/32)`) with current scores.
- **Auto-Reply**: Responds to commands in DMs, dev thread, and #memes (configurable).
- **Customization**: Configurable templates for Bio, Nickname, record announcements, and board layout.

![](static/screenshot-1.png)
![](static/screenshot-2.png)

## 🚀 Installation

1. Download and install [BetterDiscord](https://betterdiscord.app/).
2. Open Discord → **User Settings** → **BetterDiscord** → **Plugins**.
3. Click **"Open Plugins Folder"** to open `%appdata%\BetterDiscord\plugins`.
4. Drop `StankBot.plugin.js` into the folder.
5. Enable **StankBot** in the Plugins menu.

## ⚠️ Important

> **Self-Bot Warning:** Auto-replying to other users relies on your user account sending API requests without manual input, which goes against Discord's TOS regarding self-bots. Use at your own risk.

---

*Developed for the Maphra Discord Community.*
