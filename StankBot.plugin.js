/**
 * @name StankBot
 * @author randowned
 * @description Maphra community #altar management bot.
 * @version 3.0.0
 */

module.exports = class StankBot {

    // ── Point constants (edit these to tune the game) ────────────────────────
    static SP_FLAT            = 10;   // Base SP per valid stank
    static SP_STARTER_BONUS   = 15;   // Bonus for chain starter (position 1)
    static SP_FINISH_BONUS    = 15;   // Bonus retroactively given to last poster on break
    static SP_REACTION        = 1;    // SP per Stank emoji reaction
    static SP_BREAK_BASE      = 25;   // Base penalty for breaking the chain
    static SP_BREAK_PER_STANK = 2;    // Additional penalty per stank in the broken chain
    static RESTANK_COOLDOWN_MS = 10 * 60 * 1000;  // 5-minute per-user restank cooldown
    // ─────────────────────────────────────────────────────────────────────────

    toast(msg, isError = false, timeout = 5000, skipLog = false) {
        const type = isError ? "error" : "info";
        const bdUI = BdApi?.UI || BdApi;
        if (bdUI && bdUI.showToast) {
            bdUI.showToast(msg, { type: type, timeout: timeout });
        }
        if (!skipLog) this.log(msg, isError ? "ERROR" : "INFO");
    }

    log(msg, level = "INFO") {
        try {
            if (!this._logPath) {
                this._logPath = require("path").join(BdApi.Plugins.folder, "StankBot.log");
            }
            const timestamp = new Date().toISOString();
            require("fs").writeFileSync(this._logPath, "[" + timestamp + "] [" + level + "] " + msg + "\n", { flag: "a" });
        } catch (e) {
            this.toast("Log write failed: " + e.message, true, 5000, true);
        }
    }

    logSeparator() {
        try {
            if (!this._logPath) {
                this._logPath = require("path").join(BdApi.Plugins.folder, "StankBot.log");
            }
            require("fs").writeFileSync(this._logPath, "\n--- " + new Date().toISOString() + " ---\n\n", { flag: "a" });
        } catch (e) {
            this.toast("Log write failed: " + e.message, true, 5000, true);
        }
    }

    isChannelAllowed(channelId, includeAnnouncement = false) {
        const commandChannels = (this.settings.autoReplyChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean);
        const announcementChannels = includeAnnouncement ? (this.settings.announcementChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean) : [];
        const allowedChannels = [...new Set([...commandChannels, ...announcementChannels])];
        if (!this.ChannelStore) return false;
        const channel = this.ChannelStore.getChannel(channelId);
        if (!channel) return false;
        return allowedChannels.includes(channelId);
    }

    isDmAllowlisted(channelId, authorId = null) {
        if (!this.ChannelStore) return false;
        const channel = this.ChannelStore.getChannel(channelId);
        if (!channel) return false;
        // Only applies to DMs (type 1) and group DMs (type 3)
        if (channel.type !== 1 && channel.type !== 3) return false;
        const allowlist = (this.settings.dmAllowlistUserIds || "").split("\n").map(s => s.trim()).filter(Boolean);
        if (!allowlist.length) return false;
        // For the patcher (your own outgoing message): check channel recipients
        if (authorId === null) {
            const recipients = channel.recipients || [];
            return recipients.some(r => allowlist.includes(typeof r === "string" ? r : r.id));
        }
        // For processCommands (incoming message): check the author directly
        return allowlist.includes(authorId);
    }

    getPointsResponse(callerId, rankParam) {
        const sorted = Object.entries(this.stankboard).map(([id, u]) => ({ id, ...u, net: (u.xp || 0) - (u.punishments || 0) })).sort((a, b) => b.net - a.net);
        let targetId, targetRank;

        if (rankParam) {
            const requestedRank = parseInt(rankParam, 10);
            if (isNaN(requestedRank) || requestedRank < 1 || requestedRank > sorted.length) {
                return "```\nInvalid rank. Use 1-" + sorted.length + "\n```";
            }
            targetRank = requestedRank;
            targetId = sorted[requestedRank - 1].id;
        } else {
            const idx = sorted.findIndex(u => u.id === callerId);
            if (idx === -1) return "```\nYou have no Stank Points yet.\n```";
            targetRank = idx + 1;
            targetId = callerId;
        }

        const entry = this.stankboard[targetId];
        if (!entry) return "```\nUser not found.\n```";
        const xp = entry.xp || 0;
        const pun = entry.punishments || 0;
        const net = xp - pun;
        const name = entry.username || "Unknown";
        const breakdown = "\nBreakdown: " + Number(xp).toLocaleString() + " earned - " + Number(pun).toLocaleString() + " penalty";
        return "```\nRank: " + targetRank + "\nPlayer: " + name + "\nStank Points: " + Number(net).toLocaleString() + breakdown + "\n```";
    }

    getToken() {
        return this.AuthStore ? this.AuthStore.getToken() : "";
    }

    getUsername(msg) {
        const authorId = msg.author?.id;
        if (authorId === this.BOT_OWNER_ID) return this.cleanBotOwnerNick();
        const GuildMemberStore = BdApi.Webpack.getStore("GuildMemberStore");
        const memberInfo = GuildMemberStore ? GuildMemberStore.getMember(this.MAPHRA_GUILD_ID, authorId) : null;
        return memberInfo?.nick || msg.member?.nick || msg.author?.global_name || msg.author?.username || "Unknown";
    }

    isStankMessage(msg) {
        const stickers = msg.stickers || msg.stickerItems || msg.sticker_items || msg.custom_stickers || [];
        if ((!msg.content || msg.content.trim() === "") && stickers.length === 1) {
            return (stickers[0].name || "").toLowerCase().includes("stank");
        }
        return false;
    }

    ensureUser(userId, username) {
        if (!this.stankboard[userId]) {
            this.stankboard[userId] = { xp: 0, punishments: 0, username: username || "Unknown" };
        } else if (username && username !== "Unknown") {
            this.stankboard[userId].username = username;
        }
        if (this.stankboard[userId].punishments === undefined) this.stankboard[userId].punishments = 0;
    }

    applyCommonReplacements(tmpl) {
        return tmpl
            .replace(/{record}/g, this.recordChain !== null ? this.recordChain : 0)
            .replace(/{ongoing}/g, this.ongoingChain !== null ? this.ongoingChain : 0)
            .replace(/{uniqueStankers}/g, this.chainUniqueUsers ? this.chainUniqueUsers.length : 0)
            .replace(/:Stank:/g, this.STANK_EMOJI);
    }

    cleanBotOwnerNick() {
        let cleaned = this.settings.nicknameTemplate || "Randowned";
        cleaned = cleaned.replace(/\{ongoing\}/g, "").replace(/\{record\}/g, "");
        cleaned = cleaned.replace(/\s*\([^)]*\)/g, "").trim();
        return cleaned || "Randowned";
    }

    syncConfigFromDisk() {
        try {
            const fs = require("fs");
            const configPath = require("path").join(BdApi.Plugins.folder, "StankBot.config.json");
            const diskConfig = JSON.parse(fs.readFileSync(configPath, "utf8"));
            for (const key of Object.keys(diskConfig)) {
                BdApi.Data.save("StankBot", key, diskConfig[key]);
            }
            this.toast("Config loaded from disk.");
        } catch (e) {
            this.toast(`Disk config read failed, using cached: ${e.message}`);
        }
    }

    async start() {
        try {
            // Hijack BetterDiscord's toast container globally to force them to render at the Top Center!
            const bdDOM = BdApi?.DOM || BdApi;
            if (bdDOM && bdDOM.addStyle) {
                bdDOM.addStyle("StankBot-Toast", `
                    .bd-toasts, #bd-toasts {
                        position: fixed !important;
                        top: 30px !important;
                        bottom: auto !important;
                        left: 50% !important;
                        transform: translateX(-50%) !important;
                        z-index: 99999 !important;
                        display: flex !important;
                        flex-direction: column !important;
                        align-items: center !important;
                        pointer-events: none !important;
                    }
                `);
            }

            this.logSeparator();
            this.toast("Starting...", false);
            this.MAPHRA_GUILD_ID = "1482266782306799646";
            this.ALTAR_CHANNEL_ID = "1489889364392546375";
            this.STANK_EMOJI = "<a:Stank:1487854129349922816>";
            this.BOT_OWNER_ID = "129508601730564096";

            this.UserStore = BdApi.Webpack.getStore("UserStore");
            this.MessageActions = BdApi.Webpack.getModule(m => m && typeof m.sendMessage === "function" && typeof m.editMessage === "function", { searchExports: true });
            this.Dispatcher = BdApi.Webpack.getModule(m => m && typeof m.dispatch === "function" && typeof m.subscribe === "function", { searchExports: true });
            this.ChannelStore = BdApi.Webpack.getStore("ChannelStore");
            this.AuthStore = BdApi.Webpack.getStore("AuthenticationStore");

            // Sync BdApi's in-memory cache with the actual config.json file on disk
            this.syncConfigFromDisk();

            // Load Settings
            this.defaultTemplate = "```\n# Stank Board (!stank-board)\n\nChain record: {record}\nOngoing chain: {ongoing} stanks / {uniqueStankers} unique\n\n{stankBoard}\n```";
            this.defaultBioTemplate = "Current :Stank: record: {record}\nOngoing :Stank: chain: {ongoing} stanks / {uniqueStankers} unique";
            const savedSettings = BdApi.Data.load("StankBot", "settings") || {};
            this.settings = Object.assign({
                exactCommandMatch: true,
                enableNicknameSync: true,
                autoReplyChannelIds: "1483628334490587336\n1493190417703895051",
                announcementChannelIds: "1483628334490587336",
                dmAllowlistUserIds: "",
                nicknameTemplate: "Randowned ({ongoing}/{record})",
                recordTemplate: "```\n# Stank RECORD!\n\nNew chain record: {record}\nThe Slayer (chain-starter): {chainStarterServerNickname}\n\n{stankBoard}\n```",
                scoreTemplate: this.defaultTemplate,
                bioTemplate: this.defaultBioTemplate
            }, savedSettings);

            // Force update user templates to the strict new specification
            this.settings.scoreTemplate = this.defaultTemplate;

            // Reinitialize bioTemplate if missing (new update feature)
            if (!this.settings.bioTemplate) {
                this.settings.bioTemplate = this.defaultBioTemplate;
            }

            BdApi.Data.save("StankBot", "settings", this.settings);

            this.stankboard = BdApi.Data.load("StankBot", "stankboard") || {};
            // Dedupe cache for reactions (messageId:userId:emojiKey). Persisted so plugin
            // updates/reloads don't re-award past reactions. Kept as a Set in memory for
            // O(1) has/add/delete; serialized as an array on disk (insertion order preserved).
            const savedReactionKeys = BdApi.Data.load("StankBot", "processedReactions") || [];
            this.processedReactions = new Set(Array.isArray(savedReactionKeys) ? savedReactionKeys : []);

            // Chain state — all rebuilt from history on startup.
            this.recordChain = null;
            this.ongoingChain = null;        // total valid stanks in current chain
            this.chainUniqueUsers = [];      // unique user IDs (for unique-stanker count)
            this.currentChainMessageIds = new Set();
            this._seenMsgIds = new Set();
            this.lastChainContributorId = null;       // last valid stank poster (for finish bonus)
            this.lastChainContributorUsername = null;
            this.lastStankTimestamps = {};   // { [userId]: timestampMs } — cooldown tracking
            this.lastBrokenChainLength = BdApi.Data.load("StankBot", "lastBrokenChainLength") || 0;
            this.newSlayerId = BdApi.Data.load("StankBot", "newSlayerId") || null;

            // Wait for the Bio to sync before we ever listen to a single chat message
            const bioDataLoaded = await this.fetchInitialBio();

            if (!bioDataLoaded) {
                // The rule: Do not start the hooks and just end.
                this.toast("Critical Error: Failed to fetch exact scores from Bio! Plugin aborting startup.", true, 10000);
                return;
            }

            // Next, heavily synchronize the active full set natively from the #altar history deeply
            await this.syncOngoingChainFromHistory();

            // Synchronize the server nickname on startup!
            this.updateNickname();

            // ONLY activate the plugin listeners if the Bio and History data were successfully synced and confirmed
            this.onMessageCreate = this.onMessageCreate.bind(this);
            this.onMessageReactionAdd = this.onMessageReactionAdd.bind(this);
            this.onMessageReactionRemove = this.onMessageReactionRemove.bind(this);
            if (this.Dispatcher) {
                this.Dispatcher.subscribe("MESSAGE_CREATE", this.onMessageCreate);
                this.Dispatcher.subscribe("MESSAGE_REACTION_ADD", this.onMessageReactionAdd);
                this.Dispatcher.subscribe("MESSAGE_REACTION_REMOVE", this.onMessageReactionRemove);
                this.toast("Hooks active.", false, 10000);
            } else {
                this.toast("Hook failed: Dispatcher not found!", true, 10000);
            }

            BdApi.Patcher.before("StankBot", this.MessageActions, "sendMessage", (thisObject, args) => {
                const [channelId, message] = args;
                if (message && message.content) {
                    const text = message.content.trim();
                    const isAllowed = this.isChannelAllowed(channelId, text.includes("stank-help")) || this.isDmAllowlisted(channelId);
                    if ((text === "!stank-board" || text === "/stank-board") && isAllowed) {
                        message.content = this.getScoreTemplate();
                    } else if (text === "!stank-record-test" || text === "/stank-record-test") {
                        message.content = this.getRecordAnnouncementTemplate();
                    } else if ((text === "!stank-help" || text === "/stank-help") && isAllowed) {
                        message.content = this.getHelpTemplate();
                    } else if ((text.startsWith("!stank-points") || text.startsWith("/stank-points")) && isAllowed) {
                        const me = this.UserStore.getCurrentUser();
                        if (me) {
                            const parts = text.split(/\s+/);
                            const rankParam = parts.length > 1 ? parts[1] : null;
                            message.content = this.getPointsResponse(me.id, rankParam);
                        }
                    } else if (text === "!stank-board-reset" || text === "/stank-board-reset") {
                        this.resetBoard();
                        message.content = `\`\`\`\nboard reset\n\n${this.generateStankBoardAscii()}\n\`\`\``;
                    } else if (text === "!stank-board-reload" || text === "/stank-board-reload") {
                        this.resetBoard();
                        message.content = "board reloading...";
                        const reloadChannelId = channelId;
                        (async () => {
                            await this.syncOngoingChainFromHistory();
                            this.updateBio();
                            this.updateNickname();
                            this.sendBotReply(reloadChannelId, `\`\`\`\nboard reloaded\n\n${this.generateStankBoardAscii()}\n\`\`\``);
                        })();
                    }
                }
            });

        } catch (err) {
            const bdUI = BdApi.UI || BdApi;
            if (bdUI && bdUI.alert) {
                bdUI.alert("StankBot Startup Error", "Failed to start!\n\n" + (err.stack || err.toString()));
            }
        }
    }

    awardXp(userId, username, amount) {
        if (!userId) return;
        this.ensureUser(userId, username);
        this.stankboard[userId].xp += amount;
        BdApi.Data.save("StankBot", "stankboard", this.stankboard);
    }

    awardPunishment(userId, username, amount) {
        if (!userId || amount <= 0) return;
        this.ensureUser(userId, username);
        this.stankboard[userId].punishments += amount;
        BdApi.Data.save("StankBot", "stankboard", this.stankboard);
    }

    resetBoard() {
        this.stankboard = {};
        this.newSlayerId = null;
        this.lastBrokenChainLength = 0;
        this.ongoingChain = 0;
        this.chainUniqueUsers = [];
        this.currentChainMessageIds = new Set();
        this._seenMsgIds = new Set();
        this.lastChainContributorId = null;
        this.lastChainContributorUsername = null;
        this.lastStankTimestamps = {};
        BdApi.Data.save("StankBot", "stankboard", {});
        BdApi.Data.save("StankBot", "newSlayerId", null);
        BdApi.Data.save("StankBot", "lastBrokenChainLength", 0);
        BdApi.Data.save("StankBot", "lastXpMessageId", "0");
        BdApi.Data.save("StankBot", "lastPunishedMessageId", "0");
        this.toast("Board reset complete!");
    }

    generateStankBoardAscii() {
        const defaultBoardTemplate =
            "# Stank Rankings (top {stankRowsLimit})\n" +
            "Last Slayer: {slayerRank}. {slayerName} — {slayerSP} SP\n\n" +
            "{stankRankingsTable}\n\n" +
            "💀 The Chainbreaker: {chainbreakerName} ({chainbreakerPunishments} PP)";
        let tmpl = this.settings.boardLayoutTemplate || defaultBoardTemplate;

        // Refresh display names from Discord stores
        const GuildMemberStore = BdApi.Webpack.getStore("GuildMemberStore");
        if (GuildMemberStore) {
            for (const id in this.stankboard) {
                const memberInfo = GuildMemberStore.getMember(this.MAPHRA_GUILD_ID, id);
                if (memberInfo && memberInfo.nick) {
                    this.stankboard[id].username = (id === this.BOT_OWNER_ID) ? this.cleanBotOwnerNick() : memberInfo.nick;
                } else {
                    const user = this.UserStore ? this.UserStore.getUser(id) : null;
                    if (user && (user.globalName || user.username)) {
                        this.stankboard[id].username = user.globalName || user.username;
                    }
                }
            }
        }

        const stankRowsLimit = parseInt(this.settings.stankRankingRows, 10) || 5;

        // Sort by net score (earned SP - punishment points)
        const stankArr = Object.entries(this.stankboard).map(([id, u]) => ({
            id, ...u,
            net: (u.xp || 0) - (u.punishments || 0)
        })).sort((a, b) => b.net - a.net);

        // Slayer
        let slayerName = "Unknown", slayerRank = "N/A", slayerSP = 0;
        if (this.newSlayerId && this.stankboard[this.newSlayerId]) {
            slayerName = this.stankboard[this.newSlayerId].username;
            const idx = stankArr.findIndex(u => u.id === this.newSlayerId);
            if (idx !== -1) { slayerRank = idx + 1; slayerSP = stankArr[idx].net; }
        }

        // The Chainbreaker — most egregious blasphemer (highest cumulative punishment points)
        const chainbreakerEntry = Object.values(this.stankboard)
            .filter(u => (u.punishments || 0) > 0)
            .sort((a, b) => (b.punishments || 0) - (a.punishments || 0))[0];
        const chainbreakerName = chainbreakerEntry?.username || "None";
        const chainbreakerPP   = chainbreakerEntry?.punishments || 0;

        // Rankings table
        let stankTableStr = "";
        const stankTopN = stankArr.slice(0, stankRowsLimit);
        for (let i = 0; i < stankTopN.length; i++) {
            const rank = (i + 1).toString().padEnd(3, " ");
            const user = (stankTopN[i].username || "Unknown").substring(0, 20).padEnd(20, " ");
            const net  = Number(stankTopN[i].net).toLocaleString();
            stankTableStr += `${rank} | ${user} | ${net} SP\n`;
        }
        if (stankTopN.length === 0) stankTableStr += "No records yet.\n";

        tmpl = this.applyCommonReplacements(tmpl);
        tmpl = tmpl.replace(/{stankRowsLimit}/g, stankRowsLimit);
        tmpl = tmpl.replace(/{slayerRank}/g, slayerRank);
        tmpl = tmpl.replace(/{slayerName}/g, slayerName);
        tmpl = tmpl.replace(/{slayerSP}/g, Number(slayerSP).toLocaleString());
        tmpl = tmpl.replace(/{chainbreakerName}/g, chainbreakerName);
        tmpl = tmpl.replace(/{chainbreakerPunishments}/g, Number(chainbreakerPP).toLocaleString());
        tmpl = tmpl.replace(/{stankRankingsTable}/g, stankTableStr.replace(/\n$/, ""));
        // Backward-compat stubs
        tmpl = tmpl.replace(/{punishmentRankingsTable}/g, "");
        tmpl = tmpl.replace(/{punishRowsLimit}/g, "");

        return tmpl;
    }

    async syncOngoingChainFromHistory() {
        try {
            this.toast("Syncing chain from history...");

            // ── 1. Fetch messages and group them into CHAIN / GAP runs ────────────
            let allGroups = [];
            let currentGroup = [];
            let currentGroupType = null;
            let lastMessageId = null;
            let completedScrape = false;
            const token = this.getToken();

            for (let loop = 0; loop < 10 && !completedScrape; loop++) {
                let fetchUrl = `https://discord.com/api/v9/channels/${this.ALTAR_CHANNEL_ID}/messages?limit=100`;
                if (lastMessageId) fetchUrl += `&before=${lastMessageId}`;

                const res = await BdApi.Net.fetch(fetchUrl, { headers: { "Authorization": token } });
                if (!res.ok) { this.toast(`History sync error: ${await res.text()}`, true); break; }

                const messages = await res.json();
                if (!messages || messages.length === 0) break;

                for (const msg of messages) {
                    if (!msg.author?.id) continue;
                    const msgType = this.isStankMessage(msg) ? "CHAIN" : "GAP";
                    if (!currentGroupType) currentGroupType = msgType;
                    if (currentGroupType !== msgType) {
                        allGroups.push({ type: currentGroupType, messages: [...currentGroup] });
                        currentGroup = [];
                        currentGroupType = msgType;
                        const chains = allGroups.filter(g => g.type === "CHAIN").length;
                        const gaps   = allGroups.filter(g => g.type === "GAP").length;
                        if (chains >= 2 && gaps >= 2) { completedScrape = true; break; }
                    }
                    currentGroup.push(msg);
                }
                lastMessageId = messages[messages.length - 1].id;
            }

            if (currentGroup.length > 0 && !completedScrape) {
                allGroups.push({ type: currentGroupType, messages: [...currentGroup] });
            }
            if (allGroups.length === 0) return true;

            // Reverse to chronological order; then reverse each group's messages
            allGroups.reverse();
            allGroups.forEach(g => g.messages.reverse());

            // ── 2. Replay XP / punishment for new messages ────────────────────────
            let lastXp       = BdApi.Data.load("StankBot", "lastXpMessageId")        || "0";
            let lastPunished = BdApi.Data.load("StankBot", "lastPunishedMessageId")   || "0";
            let highestXp        = lastXp;
            let highestPunished  = lastPunished;
            let trackingUpdated  = false;
            let lastBrokenLength = BdApi.Data.load("StankBot", "lastBrokenChainLength") || 0;
            let runningChainTotal = 0;   // total valid stanks in the current chain group
            let seenChain = false;

            for (let g = 0; g < allGroups.length; g++) {
                const group = allGroups[g];

                if (group.type === "CHAIN") {
                    seenChain = true;
                    const isLastGroup = (g === allGroups.length - 1);
                    let position = 0;                       // valid stank counter within this group
                    const perUserLastTs = {};               // { [userId]: timestampMs } for cooldown

                    for (let i = 0; i < group.messages.length; i++) {
                        const hMsg      = group.messages[i];
                        const hAuthorId = hMsg.author.id;
                        const hUsername = this.getUsername(hMsg);
                        const hTs       = hMsg.timestamp ? Date.parse(hMsg.timestamp) : 0;
                        const prevTs    = perUserLastTs[hAuthorId] || 0;

                        // Cooldown check — same as live handler
                        if (hTs - prevTs < StankBot.RESTANK_COOLDOWN_MS) continue;
                        perUserLastTs[hAuthorId] = hTs;
                        position++;

                        if (BigInt(hMsg.id) > BigInt(lastXp)) {
                            let xp = StankBot.SP_FLAT + (position - 1);
                            if (position === 1) xp += StankBot.SP_STARTER_BONUS;

                            // For completed chains (not the last group), award finish bonus to last poster
                            const isLastInGroup = (i === group.messages.length - 1) ||
                                // check no more valid (non-cooldown) messages follow this one
                                !group.messages.slice(i + 1).some(m => {
                                    const ts = m.timestamp ? Date.parse(m.timestamp) : 0;
                                    return (ts - (perUserLastTs[m.author.id] || 0)) >= StankBot.RESTANK_COOLDOWN_MS;
                                });

                            if (!isLastGroup && isLastInGroup) xp += StankBot.SP_FINISH_BONUS;

                            this.awardXp(hAuthorId, hUsername, xp);
                            if (BigInt(hMsg.id) > BigInt(highestXp)) highestXp = hMsg.id;
                            trackingUpdated = true;
                        }
                    }
                    runningChainTotal = position;

                } else if (group.type === "GAP" && seenChain) {
                    // Only the first message in a GAP is the chain breaker
                    lastBrokenLength = runningChainTotal;
                    const breakerMsg = group.messages[0];
                    if (breakerMsg && BigInt(breakerMsg.id) > BigInt(lastPunished)) {
                        const breakerName = this.getUsername(breakerMsg);
                        const penalty = StankBot.SP_BREAK_BASE + (lastBrokenLength * StankBot.SP_BREAK_PER_STANK);
                        this.awardPunishment(breakerMsg.author.id, breakerName, penalty);
                        if (BigInt(breakerMsg.id) > BigInt(highestPunished)) highestPunished = breakerMsg.id;
                        trackingUpdated = true;
                    }
                }
            }

            // ── 3. Rebuild live chain state from the latest group ─────────────────
            const latestGroup = allGroups[allGroups.length - 1];
            if (latestGroup.type === "CHAIN") {
                let position = 0;
                const perUserLastTs = {};
                const uniqueUserIds = [];

                for (const m of latestGroup.messages) {
                    const ts     = m.timestamp ? Date.parse(m.timestamp) : 0;
                    const prevTs = perUserLastTs[m.author.id] || 0;
                    if (ts - prevTs < StankBot.RESTANK_COOLDOWN_MS) continue;
                    perUserLastTs[m.author.id] = ts;
                    position++;
                    if (!uniqueUserIds.includes(m.author.id)) uniqueUserIds.push(m.author.id);
                    // Track last contributor for finish bonus on next break
                    this.lastChainContributorId       = m.author.id;
                    this.lastChainContributorUsername = this.getUsername(m);
                    // Rebuild per-user cooldown state
                    this.lastStankTimestamps[m.author.id] = ts;
                }

                this.ongoingChain       = position;
                this.chainUniqueUsers   = uniqueUserIds;
                this.currentChainMessageIds = new Set(latestGroup.messages.map(m => m.id));

                // Slayer = chain starter (first valid poster)
                const starterMsg = latestGroup.messages.find(m => {
                    const ts = m.timestamp ? Date.parse(m.timestamp) : 0;
                    return true; // first message that passed cooldown — simplified: just use first
                });
                if (starterMsg) {
                    this.newSlayerId = starterMsg.author.id;
                    BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                }
            } else {
                // Latest group is a GAP — no ongoing chain
                this.ongoingChain   = 0;
                this.chainUniqueUsers = [];
                this.lastChainContributorId = null;
                this.lastChainContributorUsername = null;

                const recentChain = allGroups.slice().reverse().find(g => g.type === "CHAIN");
                if (recentChain?.messages.length > 0) {
                    this.newSlayerId = recentChain.messages[0].author.id;
                    BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                }
            }

            if (this.ongoingChain > this.recordChain) {
                this.recordChain = this.ongoingChain;
                BdApi.Data.save("StankBot", "recordChain", this.recordChain);
                trackingUpdated = true;
            }

            this.lastBrokenChainLength = lastBrokenLength;
            BdApi.Data.save("StankBot", "lastBrokenChainLength", this.lastBrokenChainLength);

            if (trackingUpdated) {
                BdApi.Data.save("StankBot", "lastXpMessageId", highestXp);
                BdApi.Data.save("StankBot", "lastPunishedMessageId", highestPunished);
                BdApi.Data.save("StankBot", "stankboard", this.stankboard);
            }

            this.toast(`Synced! Chain: ${this.ongoingChain} stanks / ${this.chainUniqueUsers.length} unique`, false, 8000);
            return true;
        } catch (e) {
            this.toast(`History sync failed: ${e.toString()}`, true);
            this.chainUniqueUsers = [];
            return true;
        }
    }


    async fetchInitialBio() {
        try {
            this.toast("Fetching Server Bio data...");
            const token = this.getToken();
            const me = this.UserStore ? this.UserStore.getCurrentUser() : null;
            if (!me) {
                this.toast("User ID lookup failed. Cannot fetch bio.", true);
                return false;
            }

            const res = await BdApi.Net.fetch(`https://discord.com/api/v9/users/${me.id}/profile?guild_id=${this.MAPHRA_GUILD_ID}`, {
                headers: { "Authorization": token }
            });

            if (res.ok) {
                const data = await res.json();
                const bio = data.guild_member_profile?.bio || "";

                // Intelligently construct a parser regex matching the user's custom template!
                let tmpl = this.settings.bioTemplate || this.defaultBioTemplate;
                const recordIndex = tmpl.indexOf("{record}");
                const ongoingIndex = tmpl.indexOf("{ongoing}");

                if (recordIndex === -1 || ongoingIndex === -1) {
                    this.toast(`Bio fetch aborted: Settings template missing {record} or {ongoing} variables!`, true, 10000);
                    return false;
                }

                let regexStr = tmpl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape regex syntax literals safely
                regexStr = regexStr.replace(/\\{record\\}/g, "(\\d+)");
                regexStr = regexStr.replace(/\\{ongoing\\}/g, "(\\d+)");
                regexStr = regexStr.replace(/:Stank:/g, ".*?"); // Allow raw text or full animated custom emoji string
                regexStr = regexStr.replace(/\n|\r/g, "\\s*");  // Allow newlines mapping gracefully

                const matcher = new RegExp(regexStr, "i");
                const match = bio.match(matcher);

                let parserSuccess = false;
                if (match && match.length >= 3) {
                    // Evaluate based on which placeholder appeared first in the template UI string natively
                    if (recordIndex < ongoingIndex) {
                        this.recordChain = parseInt(match[1], 10);
                        this.ongoingChain = parseInt(match[2], 10);
                    } else {
                        this.ongoingChain = parseInt(match[1], 10);
                        this.recordChain = parseInt(match[2], 10);
                    }
                    parserSuccess = true;
                } else {
                    // Aggressive last-resort fallback mapping in case the UI template changed and Bio isn't updated yet 
                    const fbRecord = bio.match(/record?\D*?(\d+)/i);
                    const fbOngoing = bio.match(/ongoing?\D*?(\d+)/i);
                    if (fbRecord && fbOngoing) {
                        this.recordChain = parseInt(fbRecord[1], 10);
                        this.ongoingChain = parseInt(fbOngoing[1], 10);
                        parserSuccess = true;
                    }
                }

                // Validation rule: Make sure values actually properly bound
                if (!parserSuccess || this.recordChain === null || this.ongoingChain === null || isNaN(this.recordChain) || isNaN(this.ongoingChain)) {
                    this.toast(`Bio fetch succeeded, but text completely failed to parse for scores!`, true);
                    return false;
                }

                this.toast(`Loaded! Record: ${this.recordChain}, Bio Ongoing: ${this.ongoingChain}`);
                return true;
            } else {
                this.toast(`Bio fetch failed. API status: ${res.status}`, true);
                return false;
            }
        } catch (e) {
            this.toast(`Fetch error: ${e.toString()}`, true);
            return false;
        }
    }

    stop() {
        this.toast("Stopping...");
        if (this.Dispatcher) {
            this.Dispatcher.unsubscribe("MESSAGE_CREATE", this.onMessageCreate);
            this.Dispatcher.unsubscribe("MESSAGE_REACTION_ADD", this.onMessageReactionAdd);
            this.Dispatcher.unsubscribe("MESSAGE_REACTION_REMOVE", this.onMessageReactionRemove);
        }
        BdApi.Patcher.unpatchAll("StankBot");

        const bdDOM = BdApi?.DOM || BdApi;
        if (bdDOM && bdDOM.removeStyle) {
            bdDOM.removeStyle("StankBot-Toast");
        }
    }

    async updateNickname() {
        let targetNick = "Randowned";
        if (this.settings.enableNicknameSync) {
            targetNick = this.applyCommonReplacements(this.settings.nicknameTemplate || "Randowned ({ongoing}/{record})");
        }


        const token = this.getToken();
        try {
            const res = await BdApi.Net.fetch(`https://discord.com/api/v9/guilds/${this.MAPHRA_GUILD_ID}/members/@me`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": token
                },
                body: JSON.stringify({ nick: targetNick })
            });
            if (res.ok) {
                this.toast(`Nickname updated to: ${targetNick}`);
            } else {
                const text = await res.text();
                this.toast(`Nickname sync failed! ${res.status}: ${text.substring(0, 50)}`, true);
            }
        } catch (err) {
            this.toast(`Nickname patch crash! ${err.toString()}`, true);
        }
    }

    getScoreTemplate() {
        let tmpl = this.applyCommonReplacements(this.settings.scoreTemplate || this.defaultTemplate);
        tmpl = tmpl.replace(/{stankBoard}/g, this.generateStankBoardAscii());
        return tmpl;
    }

    getBioTemplate() {
        return this.applyCommonReplacements(this.settings.bioTemplate || this.defaultBioTemplate);
    }

    getRecordAnnouncementTemplate() {
        let tmpl = this.applyCommonReplacements(this.settings.recordTemplate || "```\nnew record chain: {record}\n\n{stankBoard}\n```");

        let slayerName = "Unknown";
        if (this.newSlayerId) {
            const GuildMemberStore = BdApi.Webpack.getStore("GuildMemberStore");
            const memberInfo = GuildMemberStore ? GuildMemberStore.getMember(this.MAPHRA_GUILD_ID, this.newSlayerId) : null;
            if (memberInfo?.nick) {
                slayerName = (this.newSlayerId === this.BOT_OWNER_ID) ? this.cleanBotOwnerNick() : memberInfo.nick;
            } else if (this.stankboard[this.newSlayerId]?.username) {
                slayerName = this.stankboard[this.newSlayerId].username;
            }
        }
        tmpl = tmpl.replace(/{chainStarterServerNickname}/g, slayerName);
        tmpl = tmpl.replace(/{stankBoard}/g, this.generateStankBoardAscii());

        return tmpl;
    }

    getHelpTemplate() {
        return `\`\`\`markdown
# StankBot (!stank-help)

## Commands - only in #stankbot
!stank-board - the leaderboard
!stank-points - your Stank Points and rank
!stank-points <rank> - look up a player by rank
!stank-help - this help message

## Stank Points
- 10 + pos-1 SP: valid Stank sticker (streak bonus based on position in chain)
-        +15 SP: chain starter bonus (first stank)
-        +15 SP: retroactive bonus to the last poster when chain breaks
-         +1 SP: Stank emoji reaction on an ongoing-chain sticker (once per user per sticker)

## Punishment Points
- 25 + (chain length × 2) PP: breaking the chain

## Cooldown
- Same user cannot stank again for 5 minutes (per-user cooldown per chain)
\`\`\``;
    }

    updateBio() {
        const token = this.getToken();
        BdApi.Net.fetch(`https://discord.com/api/v9/guilds/${this.MAPHRA_GUILD_ID}/profile/@me`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "Authorization": token
            },
            body: JSON.stringify({ bio: this.getBioTemplate() })
        })
            .then(async res => {
                if (res.ok) {
                    this.toast(`Bio fully updated!`);
                } else {
                    const text = await res.text();
                    // We add the exact error message text from Discord here for debugging
                    this.toast(`Bio API push failed! ${res.status}: ${text.substring(0, 70)}`, true);
                }
            })
            .catch(err => this.toast(`Bio patch crash! ${err.toString()}`, true));
    }

    async sendBotReply(channelId, textContent, replyToMessageId = null) {
        const token = this.getToken();
        try {
            const body = { content: textContent };
            if (replyToMessageId) {
                body.message_reference = { message_id: replyToMessageId };
            }

            const res = await BdApi.Net.fetch(`https://discord.com/api/v9/channels/${channelId}/messages`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": token
                },
                body: JSON.stringify(body)
            });


            if (!res.ok) {
                const text = await res.text();
                this.toast(`Auto-reply failed! ${res.status}: ${text.substring(0, 50)}`, true);
            }
        } catch (e) {
            this.toast(`Auto-reply crash! ${e.toString()}`, true);
        }
    }

    async addStankReaction(channelId, messageId) {
        const token = this.getToken();
        const emojiUri = encodeURIComponent("Stank:1487854129349922816");

        // Pre-block the bot's own auto-reaction from awarding SP.
        // The REMOVE handler will clear this key if the operator manually un-reacts.
        const me = this.UserStore?.getCurrentUser();
        if (me) {
            const reactionKey = `${messageId}:${me.id}:1487854129349922816`;
            this.processedReactions.add(reactionKey);
            BdApi.Data.save("StankBot", "processedReactions", Array.from(this.processedReactions));
        }

        try {
            await BdApi.Net.fetch(`https://discord.com/api/v9/channels/${channelId}/messages/${messageId}/reactions/${emojiUri}/@me`, {
                method: "PUT",
                headers: { "Authorization": token }
            });
        } catch (e) {
            this.toast(`Failed to react: ${e.toString()}`, true);
        }
    }

    onMessageReactionAdd(event) {
        try {
            if (!event) return;
            if (event.channelId !== this.ALTAR_CHANNEL_ID) return;
            const emojiName = event.emoji?.name?.toLowerCase() || "";
            if (emojiName.includes("stank") || event.emoji?.id === "1487854129349922816") {
                // Only award on Stank stickers that belong to the current ongoing chain.
                if (!this.currentChainMessageIds.has(event.messageId)) return;
                const userId = event.userId;
                const emojiKey = event.emoji?.id || event.emoji?.name || "";
                const reactionKey = `${event.messageId}:${userId}:${emojiKey}`;
                if (this.processedReactions.has(reactionKey)) return;
                this.processedReactions.add(reactionKey);
                BdApi.Data.save("StankBot", "processedReactions", Array.from(this.processedReactions));
                const GuildMemberStore = BdApi.Webpack.getStore("GuildMemberStore");
                const memberInfo = GuildMemberStore ? GuildMemberStore.getMember(this.MAPHRA_GUILD_ID, userId) : null;
                const user = this.UserStore?.getUser(userId);
                const username = memberInfo?.nick || user?.globalName || user?.username || "Unknown";
                this.awardXp(userId, username, StankBot.SP_REACTION);
                this.toast(`+${StankBot.SP_REACTION} SP -> ${username} (reaction)`);
            }
        } catch (e) {
            this.toast(`Reaction error: ${e.message}`, true);
        }
    }

    onMessageReactionRemove(event) {
        try {
            if (!event) return;
            if (event.channelId !== this.ALTAR_CHANNEL_ID) return;
            // Only the plugin operator is allowed to remove+re-add to re-earn SP.
            // For everyone else, leaving the dedupe key in place blocks remove+re-add exploits.
            const me = this.UserStore?.getCurrentUser();
            if (!me || event.userId !== me.id) return;
            const emojiName = event.emoji?.name?.toLowerCase() || "";
            if (emojiName.includes("stank") || event.emoji?.id === "1487854129349922816") {
                const emojiKey = event.emoji?.id || event.emoji?.name || "";
                const reactionKey = `${event.messageId}:${event.userId}:${emojiKey}`;
                if (this.processedReactions.delete(reactionKey)) {
                    BdApi.Data.save("StankBot", "processedReactions", Array.from(this.processedReactions));
                }
            }
        } catch (e) {
            this.toast(`Reaction remove error: ${e.message}`, true);
        }
    }

    onMessageCreate(event) {
        if (!event || !event.message) return;
        const msg = event.message;

        if (msg.channel_id === this.ALTAR_CHANNEL_ID) {
            try {
                this.processAltarMessage(msg);
            } catch (e) {
                this.toast(`Altar error: ${e.message}`, true);
            }
        }

        try {
            this.processCommands(msg);
        } catch (e) {
            this.toast(`Command error: ${e.message}`, true);
        }
    }

    processAltarMessage(msg) {
        const isStank = this.isStankMessage(msg);
        let stateChanged = false;

        if (isStank) {
            const authorId = msg.author?.id;
            if (!authorId) return;

            // Discord dispatches MESSAGE_CREATE multiple times per message — deduplicate
            if (this._seenMsgIds.has(msg.id)) return;
            this._seenMsgIds.add(msg.id);

            const username = this.getUsername(msg);
            const msgTs = msg.timestamp ? Date.parse(msg.timestamp) : Date.now();
            const lastTs = this.lastStankTimestamps[authorId] || 0;

            if (msgTs - lastTs < StankBot.RESTANK_COOLDOWN_MS) {
                // Cooldown violation — react but award nothing; don't add to chain
                this.addStankReaction(msg.channel_id, msg.id);
                const secsLeft = Math.ceil((StankBot.RESTANK_COOLDOWN_MS - (msgTs - lastTs)) / 1000);
                const commandChannels = (this.settings.autoReplyChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean);
                for (const ch of commandChannels) {
                    this.sendBotReply(ch, `⏳ ${username}, restank cooldown! Wait ${secsLeft}s.`);
                }
                this.toast(`⏳ ${username} restanked too soon (${secsLeft}s left)`);
                return;
            }

            // Valid stank — track for reaction eligibility
            this.currentChainMessageIds.add(msg.id);

            // Valid stank — advance chain
            this.ongoingChain += 1;
            if (!this.chainUniqueUsers.includes(authorId)) this.chainUniqueUsers.push(authorId);
            this.lastStankTimestamps[authorId] = msgTs;
            this.lastChainContributorId = authorId;
            this.lastChainContributorUsername = username;

            this.addStankReaction(msg.channel_id, msg.id);

            let xp = StankBot.SP_FLAT + (this.ongoingChain - 1);
            if (this.ongoingChain === 1) {
                xp += StankBot.SP_STARTER_BONUS;
                this.newSlayerId = authorId;
                BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
            }

            this.awardXp(authorId, username, xp);
            this.toast(`+${xp} SP -> ${username} (chain #${this.ongoingChain})`);
            BdApi.Data.save("StankBot", "lastXpMessageId", msg.id);
            stateChanged = true;

        } else if (this.ongoingChain > 0 || this.chainUniqueUsers.length > 0) {
            // Chain break
            const authorId = msg.author?.id;
            const username = this.getUsername(msg);

            // Award finish bonus to the last valid poster
            if (this.lastChainContributorId) {
                this.awardXp(this.lastChainContributorId, this.lastChainContributorUsername, StankBot.SP_FINISH_BONUS);
                this.toast(`+${StankBot.SP_FINISH_BONUS} SP -> ${this.lastChainContributorUsername} (chain finish!)`);
            }

            // Punish chain breaker
            const brokenLength = this.ongoingChain;
            this.lastBrokenChainLength = brokenLength;
            BdApi.Data.save("StankBot", "lastBrokenChainLength", this.lastBrokenChainLength);

            if (authorId) {
                const penalty = StankBot.SP_BREAK_BASE + (brokenLength * StankBot.SP_BREAK_PER_STANK);
                this.awardPunishment(authorId, username, penalty);
                this.toast(`💥 ${username} broke chain of ${brokenLength} → -${penalty} PP`);
                BdApi.Data.save("StankBot", "lastPunishedMessageId", msg.id);

                // Callout in command channels
                const commandChannels = (this.settings.autoReplyChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean);
                for (const ch of commandChannels) {
                    this.sendBotReply(ch, `💥 **${username}** broke the Stank chain at **${brokenLength}** stanks! (-${penalty} PP)`);
                }
            }

            // Record check
            if (this.ongoingChain > this.recordChain) {
                this.recordChain = this.ongoingChain;
                if ((this.settings.recordTemplate || "").trim()) {
                    this.toast(`🎉 New record! Announcing...`);
                    const announcement = this.getRecordAnnouncementTemplate();
                    const channels = (this.settings.announcementChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean);
                    for (const ch of channels) this.sendBotReply(ch, announcement);
                } else {
                    this.toast(`🎉 New record! (no announcement template)`);
                }
            }

            // Reset chain state
            this.ongoingChain = 0;
            this.chainUniqueUsers = [];
            this.currentChainMessageIds.clear();
            this._seenMsgIds.clear();
            this.processedReactions.clear();
            BdApi.Data.save("StankBot", "processedReactions", []);
            this.lastChainContributorId = null;
            this.lastChainContributorUsername = null;
            this.lastStankTimestamps = {};
            stateChanged = true;
        }

        if (stateChanged) {
            this.updateBio();
            this.updateNickname();
        }
    }

    processCommands(msg) {
        const me = this.UserStore.getCurrentUser();
        // We only auto-reply to other people
        if (!me || !msg.author || msg.author.id === me.id) return;

        if (!msg.content) return;
        const rawContent = msg.content.trim();
        const match = (cmd) => this.settings.exactCommandMatch ? (rawContent === cmd) : msg.content.includes(cmd);

        // Admin commands; silently ignore from non-admin users
        if (match("!stank-board-reset") || match("!stank-board-reload") ||
            match("!stank-record-test")) return;

        let isBoardCommand = match("!stank-board");
        let isXpCommand = rawContent === "!stank-points" || rawContent.startsWith("!stank-points ");
        let isHelpCommand = match("!stank-help");

        if (!isBoardCommand && !isXpCommand && !isHelpCommand) return;

        const isAllowlisted = this.isChannelAllowed(msg.channel_id, isHelpCommand);
        const isDmAllowlisted = !msg.guild_id && this.isDmAllowlisted(msg.channel_id, msg.author.id);

        if (!isAllowlisted && !isDmAllowlisted) return;

        if (isXpCommand) {
            const parts = rawContent.split(/\s+/);
            const rankParam = parts.length > 1 ? parts[1] : null;
            const replyText = this.getPointsResponse(msg.author.id, rankParam);
            this.sendBotReply(msg.channel_id, replyText, msg.id);
        } else if (isBoardCommand) {
            this.sendBotReply(msg.channel_id, this.getScoreTemplate());
        } else if (isHelpCommand) {
            this.sendBotReply(msg.channel_id, this.getHelpTemplate(), msg.id);
        }
    }

    // Settings Panel Factory Helpers

    _addNote(parent, text) {
        const note = document.createElement("div");
        Object.assign(note.style, { marginTop: "4px", marginBottom: "16px", fontSize: "12px", color: "var(--text-muted)", lineHeight: "1.4" });
        note.innerText = text;
        parent.appendChild(note);
    }

    _addCheckbox(parent, label, settingKey, note, onChange) {
        const container = document.createElement("label");
        Object.assign(container.style, { display: "flex", alignItems: "center", gap: "8px", fontSize: "14px", cursor: "pointer", marginBottom: "2px" });

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = this.settings[settingKey];
        Object.assign(checkbox.style, { width: "18px", height: "18px", cursor: "pointer", accentColor: "#5865f2" });

        checkbox.addEventListener("change", (e) => {
            this.settings[settingKey] = e.target.checked;
            BdApi.Data.save("StankBot", "settings", this.settings);
            this.toast(`${label}: ${e.target.checked ? "ON" : "OFF"}`);
            if (onChange) onChange(e.target.checked);
        });

        container.appendChild(checkbox);
        container.appendChild(document.createTextNode(label));
        parent.appendChild(container);
        if (note) this._addNote(parent, note);
    }

    _addTextarea(parent, label, value, height, note, onChange) {
        const lbl = document.createElement("div");
        Object.assign(lbl.style, { fontSize: "14px", fontWeight: "500", marginBottom: "6px", color: "var(--header-secondary)" });
        lbl.textContent = label;
        parent.appendChild(lbl);

        const textarea = document.createElement("textarea");
        textarea.value = value;
        Object.assign(textarea.style, {
            width: "100%", height: height, fontFamily: "monospace", fontSize: "13px", padding: "8px",
            backgroundColor: "var(--input-background, rgba(0,0,0,0.4))", color: "var(--text-normal)",
            border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px", resize: "vertical",
            boxSizing: "border-box"
        });
        textarea.addEventListener("change", (e) => onChange(e.target.value.trim(), e));

        parent.appendChild(textarea);
        if (note) this._addNote(parent, note);
    }

    _addNumberInput(parent, label, settingKey, defaultVal) {
        const container = document.createElement("div");
        Object.assign(container.style, { display: "flex", alignItems: "center", gap: "8px", fontSize: "14px", marginBottom: "10px" });

        const lbl = document.createElement("span");
        Object.assign(lbl.style, { color: "var(--header-secondary)", fontWeight: "500" });
        lbl.textContent = label;
        container.appendChild(lbl);

        const input = document.createElement("input");
        input.type = "number";
        input.min = "1";
        input.max = "100";
        input.value = this.settings[settingKey] || defaultVal;
        Object.assign(input.style, {
            width: "55px", padding: "4px 6px", fontSize: "13px", fontFamily: "monospace",
            backgroundColor: "var(--input-background, rgba(0,0,0,0.4))", color: "var(--text-normal)",
            border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px"
        });

        input.addEventListener("change", (e) => {
            let val = parseInt(e.target.value, 10);
            if (isNaN(val) || val < 1) val = defaultVal;
            this.settings[settingKey] = val;
            BdApi.Data.save("StankBot", "settings", this.settings);
        });

        container.appendChild(input);
        parent.appendChild(container);
    }

    _addTextInput(parent, label, value, note, onChange) {
        const lbl = document.createElement("div");
        Object.assign(lbl.style, { fontSize: "14px", fontWeight: "500", marginBottom: "6px", color: "var(--header-secondary)" });
        lbl.textContent = label;
        parent.appendChild(lbl);

        const input = document.createElement("input");
        input.type = "text";
        input.value = value;
        Object.assign(input.style, {
            width: "100%", padding: "8px", fontSize: "13px", fontFamily: "monospace",
            backgroundColor: "var(--input-background, rgba(0,0,0,0.4))", color: "var(--text-normal)",
            border: "1px solid rgba(255,255,255,0.1)", borderRadius: "4px",
            boxSizing: "border-box"
        });
        input.addEventListener("change", (e) => onChange(e.target.value.trim()));

        parent.appendChild(input);
        if (note) this._addNote(parent, note);
    }

    // Settings Panel

    getSettingsPanel() {
        const panel = document.createElement("div");
        Object.assign(panel.style, { padding: "16px", color: "var(--text-normal)", maxWidth: "600px" });

        const createSection = (title) => {
            const header = document.createElement("div");
            Object.assign(header.style, {
                fontSize: "12px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.5px",
                color: "var(--header-secondary)", marginBottom: "12px", paddingBottom: "6px",
                borderBottom: "1px solid rgba(255,255,255,0.06)"
            });
            header.textContent = title;

            const section = document.createElement("div");
            Object.assign(section.style, { marginBottom: "24px" });
            section.appendChild(header);
            return section;
        };

        // Core
        const sCore = createSection("Behavior");

        this._addCheckbox(sCore, "Sync server nickname with chain", "enableNicknameSync",
            "Auto-update your Maphra nickname on chain changes. Discord limits ~10 changes/hour.",
            () => this.updateNickname());

        this._addCheckbox(sCore, "Require exact text match for commands", "exactCommandMatch",
            "Only trigger when the command is the entire message content.");

        this._addTextarea(sCore, "Command channels",
            this.settings.autoReplyChannelIds || "", "55px",
            "Channel IDs for command auto-replies (one per line). Threads inherit. DMs always work.",
            (val) => {
                this.settings.autoReplyChannelIds = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Command channels updated!");
            });

        this._addTextarea(sCore, "Announcement channels",
            this.settings.announcementChannelIds || "", "55px",
            "Channel IDs for record-broken announcements (one per line).",
            (val) => {
                this.settings.announcementChannelIds = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Announcement channels updated!");
            });

        this._addTextarea(sCore, "DM allowlist",
            this.settings.dmAllowlistUserIds || "", "55px",
            "User IDs allowed to use commands via DMs or group chats (one per line).",
            (val) => {
                this.settings.dmAllowlistUserIds = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("DM allowlist updated!");
            });

        // Templates
        const sTemplates = createSection("Templates");

        this._addNumberInput(sTemplates, "Stank ranking rows:", "stankRankingRows", 5);

        this._addTextarea(sTemplates, "Bio layout",
            this.settings.bioTemplate || this.defaultBioTemplate, "55px",
            "Your Discord server bio. Must contain {record} and {ongoing}. Syncs on change.",
            (val, e) => {
                if (!val.includes("{record}") || !val.includes("{ongoing}")) {
                    this.toast("Bio template must contain both {record} and {ongoing}!", true);
                    e.target.value = this.settings.bioTemplate || this.defaultBioTemplate;
                    return;
                }
                this.settings.bioTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Bio Template Saved!");
                this.updateBio();
            });

        const defaultBoardTemplate = "# Stank Rankings (top {stankRowsLimit})\nLast Slayer: {slayerRank}. {slayerName} — {slayerSP} SP\n\n{stankRankingsTable}\n\n💀 The Chainbreaker: {chainbreakerName} ({chainbreakerPunishments} PP)";

        this._addTextarea(sTemplates, "Leaderboard layout ({stankBoard})",
            this.settings.boardLayoutTemplate || defaultBoardTemplate, "140px",
            "Layout for {stankBoard}. Vars: {record}, {ongoing}, {uniqueStankers}, {stankRowsLimit}, {slayerRank}, {slayerName}, {slayerSP}, {chainbreakerName}, {chainbreakerPunishments}, {stankRankingsTable}",
            (val) => {
                this.settings.boardLayoutTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("StankBoard Format Saved!");
            });

        this._addTextarea(sTemplates, "Board reply format",
            this.settings.scoreTemplate || this.defaultTemplate, "55px",
            "Reply layout for !stank-board. Vars: {record}, {ongoing}, {stankBoard}, :Stank:",
            (val) => {
                this.settings.scoreTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Score Template Saved!");
            });

        this._addTextarea(sTemplates, "Record broken announcement",
            this.settings.recordTemplate || "", "80px",
            "Leave empty to disable. Vars: {record}, {stankBoard}, {chainStarterServerNickname}, :Stank:",
            (val) => {
                this.settings.recordTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Record Announcement Template Saved!");
            });

        this._addTextInput(sTemplates, "Nickname format",
            this.settings.nicknameTemplate || "Randowned ({ongoing}/{record})",
            "Used when nickname sync is on. Vars: {record}, {ongoing}",
            (val) => {
                this.settings.nicknameTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Nickname Template Saved!");
                if (this.settings.enableNicknameSync) this.updateNickname();
            });

        panel.appendChild(sCore);
        panel.appendChild(sTemplates);
        return panel;
    }
};

