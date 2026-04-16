/**
 * @name StankBot
 * @author randowned
 * @description Maphra community #altar management bot.
 * @version 2.2.0
 */

module.exports = class StankBot {
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
        return msg.member?.nick || msg.author?.global_name || msg.author?.username || "Unknown";
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
            this.stankboard[userId] = { xp: 0, punishments: 0, username: username || "Unknown", hasPostedSticker: false };
        } else if (username && this.stankboard[userId].username === "Unknown" && username !== "Unknown") {
            this.stankboard[userId].username = username;
        }
        if (this.stankboard[userId].punishments === undefined) this.stankboard[userId].punishments = 0;
    }

    applyCommonReplacements(tmpl) {
        return tmpl
            .replace(/{record}/g, this.recordChain !== null ? this.recordChain : 0)
            .replace(/{ongoing}/g, this.ongoingChain !== null ? this.ongoingChain : 0)
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
            this.CHEATER_CAUGHT_GIF = "https://tenor.com/view/bh187-austin-powers-spotlight-search-light-busted-gif-19285562";
            this.BOT_OWNER_ID = "129508601730564096";

            this.UserStore = BdApi.Webpack.getStore("UserStore");
            this.MessageActions = BdApi.Webpack.getModule(m => m && typeof m.sendMessage === "function" && typeof m.editMessage === "function", { searchExports: true });
            this.Dispatcher = BdApi.Webpack.getModule(m => m && typeof m.dispatch === "function" && typeof m.subscribe === "function", { searchExports: true });
            this.ChannelStore = BdApi.Webpack.getStore("ChannelStore");
            this.AuthStore = BdApi.Webpack.getStore("AuthenticationStore");

            // Sync BdApi's in-memory cache with the actual config.json file on disk
            this.syncConfigFromDisk();

            // Load Settings
            this.defaultTemplate = "```\n# Stank Board (!stank-board)\n\nChain record: {record}\nOngoing chain: {ongoing}\n\n{stankBoard}\n```";
            this.defaultBioTemplate = "Current :Stank: record: {record}\nOngoing :Stank: chain: {ongoing}";
            const savedSettings = BdApi.Data.load("StankBot", "settings") || {};
            this.settings = Object.assign({
                exactCommandMatch: true,
                enableNicknameSync: true,
                autoReplyChannelIds: "1483628334490587336\n1493190417703895051",
                announcementChannelIds: "1483628334490587336",
                nicknameTemplate: "Randowned ({ongoing}/{record})",
                recordTemplate: "```\n# Stank RECORD!\n\nNew chain record: {record}\nThe Slayer (chain-starter): {chainStarterServerNickname}\n\n{stankBoard}\n```",
                cheaterTemplate: "{username} - penalty! - 50 punishment points awarded!",
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

            // We entirely remove the defaults. They must be fetched from the API.
            this.recordChain = null;
            this.ongoingChain = null;
            this.chainUniqueUsers = [];
            this.lastBrokenChainLength = BdApi.Data.load("StankBot", "lastBrokenChainLength") || 0;
            this.newSlayerId = BdApi.Data.load("StankBot", "newSlayerId") || null;
            this.newGoatId = BdApi.Data.load("StankBot", "newGoatId") || null;
            this.lastChainWasCheaterStart = BdApi.Data.load("StankBot", "lastChainWasCheaterStart") || false;

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
            if (this.Dispatcher) {
                this.Dispatcher.subscribe("MESSAGE_CREATE", this.onMessageCreate);
                this.Dispatcher.subscribe("MESSAGE_REACTION_ADD", this.onMessageReactionAdd);
                this.toast("Hooks active.", false, 10000);
            } else {
                this.toast("Hook failed: Dispatcher not found!", true, 10000);
            }

            BdApi.Patcher.before("StankBot", this.MessageActions, "sendMessage", (thisObject, args) => {
                const [channelId, message] = args;
                if (message && message.content) {
                    const text = message.content.trim();
                    const isAllowed = this.isChannelAllowed(channelId, text.includes("stank-help"));
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
                    } else if (text === "!stank-cheater-test" || text === "/stank-cheater-test") {
                        const testUser = this.UserStore?.getCurrentUser();
                        const memberStore = BdApi.Webpack.getStore("GuildMemberStore");
                        const memberInfo = testUser && memberStore ? memberStore.getMember(this.MAPHRA_GUILD_ID, testUser.id) : null;
                        const myName = memberInfo?.nick || testUser?.globalName || testUser?.username || "Unknown";
                        this.sendCheaterMessage(testUser?.id, myName, channelId);
                        message.content = "!stank-cheater-test";
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
        this.newGoatId = null;
        this.lastBrokenChainLength = 0;
        this.ongoingChain = 0;
        this.chainUniqueUsers = [];
        BdApi.Data.save("StankBot", "stankboard", {});
        BdApi.Data.save("StankBot", "newSlayerId", null);
        BdApi.Data.save("StankBot", "newGoatId", null);
        BdApi.Data.save("StankBot", "lastBrokenChainLength", 0);
        BdApi.Data.save("StankBot", "lastXpMessageId", "0");
        BdApi.Data.save("StankBot", "lastPunishedMessageId", "0");
        this.toast("Board reset complete!");
    }

    generateStankBoardAscii() {
        const defaultBoardTemplate = "# Stank Rankings (top {stankRowsLimit})\nlast slayer: {slayerRank}, {slayerName}, {slayerSP} SP\nlast goat: {goatRank}, {goatName}, {goatSP} PP\n\n{stankRankingsTable}";
        let tmpl = this.settings.boardLayoutTemplate || defaultBoardTemplate;

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

        // Sort by net score (xp - punishments), stored separately
        const stankArr = Object.entries(this.stankboard).map(([id, u]) => ({
            id, ...u,
            net: (u.xp || 0) - (u.punishments || 0)
        })).sort((a, b) => b.net - a.net);

        let slayerName = "Unknown";
        let slayerRank = "N/A";
        let slayerSP = 0;
        if (this.newSlayerId && this.stankboard[this.newSlayerId]) {
            slayerName = this.stankboard[this.newSlayerId].username;
            const idx = stankArr.findIndex(u => u.id === this.newSlayerId);
            if (idx !== -1) { slayerRank = idx + 1; slayerSP = stankArr[idx].net; }
        }

        let goatName = "None";
        let goatRank = "N/A";
        let goatSP = 0;
        if (this.newGoatId && this.stankboard[this.newGoatId]) {
            goatName = this.stankboard[this.newGoatId].username;
            const idx = stankArr.findIndex(u => u.id === this.newGoatId);
            if (idx !== -1) { goatRank = idx + 1; goatSP = stankArr[idx].net; }
        }

        tmpl = this.applyCommonReplacements(tmpl);
        tmpl = tmpl.replace(/{stankRowsLimit}/g, stankRowsLimit);
        tmpl = tmpl.replace(/{slayerRank}/g, slayerRank);
        tmpl = tmpl.replace(/{slayerName}/g, slayerName);
        tmpl = tmpl.replace(/{slayerSP}/g, Number(slayerSP).toLocaleString());
        tmpl = tmpl.replace(/{goatRank}/g, goatRank);
        tmpl = tmpl.replace(/{goatName}/g, goatName);
        tmpl = tmpl.replace(/{goatSP}/g, Number(goatSP).toLocaleString());

        // Stank Table - single unified ranking by net score
        let stankTableStr = "";
        const stankTopN = stankArr.slice(0, stankRowsLimit);
        for (let i = 0; i < stankTopN.length; i++) {
            const rank = (i + 1).toString().padEnd(3, " ");
            const user = (stankTopN[i].username || "Unknown").substring(0, 20).padEnd(20, " ");
            const net = Number(stankTopN[i].net).toLocaleString();
            const pun = stankTopN[i].punishments || 0;
            stankTableStr += `${rank} | ${user} | ${net} Stank Points\n`;
        }
        if (stankTopN.length === 0) stankTableStr += "No records yet.\n";
        tmpl = tmpl.replace(/{stankRankingsTable}/g, stankTableStr.replace(/\n$/, ""));
        // Keep backward compat for punishment table placeholder
        tmpl = tmpl.replace(/{punishmentRankingsTable}/g, "");
        tmpl = tmpl.replace(/{punishRowsLimit}/g, "");

        return tmpl;
    }

    async syncOngoingChainFromHistory() {
        try {
            this.toast("Syncing chain from history...");
            let allGroups = [];
            let currentGroup = [];
            let currentGroupType = null;
            let lastMessageId = null;

            let completedScrape = false;
            let loopLimit = 10;
            let currentLoop = 0;

            const token = this.getToken();

            while (!completedScrape && currentLoop < loopLimit) {
                currentLoop++;
                let fetchUrl = `https://discord.com/api/v9/channels/${this.ALTAR_CHANNEL_ID}/messages?limit=100`;
                if (lastMessageId) fetchUrl += `&before=${lastMessageId}`;

                const res = await BdApi.Net.fetch(fetchUrl, { headers: { "Authorization": token } });
                if (!res.ok) {
                    this.toast(`History sync error: ${await res.text()}`, true);
                    break;
                }

                const messages = await res.json();
                if (!messages || messages.length === 0) {
                    break;
                }

                for (let i = 0; i < messages.length; i++) {
                    const msg = messages[i];
                    const isStank = this.isStankMessage(msg);

                    if (!msg.author?.id) continue;

                    const msgType = isStank ? "CHAIN" : "GAP";

                    if (!currentGroupType) {
                        currentGroupType = msgType;
                    }

                    if (currentGroupType !== msgType) {
                        allGroups.push({ type: currentGroupType, messages: [...currentGroup] });
                        currentGroup = [];
                        currentGroupType = msgType;

                        let chainCount = allGroups.filter(g => g.type === "CHAIN").length;
                        let gapCount = allGroups.filter(g => g.type === "GAP").length;
                        if (chainCount >= 2 && gapCount >= 2) {
                            completedScrape = true;
                            break;
                        }
                    }
                    currentGroup.push(msg);
                }
                lastMessageId = messages[messages.length - 1].id;
            }

            if (currentGroup.length > 0 && !completedScrape) {
                allGroups.push({ type: currentGroupType, messages: [...currentGroup] });
            }

            if (allGroups.length === 0) return true;

            allGroups.reverse();

            let lastXp = BdApi.Data.load("StankBot", "lastXpMessageId") || "0";
            let lastPunished = BdApi.Data.load("StankBot", "lastPunishedMessageId") || "0";
            let highestXpInBatch = lastXp;
            let highestPunishedInBatch = lastPunished;

            let trackingUpdated = false;

            allGroups.forEach(group => group.messages.reverse());

            let lastBrokenLengthTracker = BdApi.Data.load("StankBot", "lastBrokenChainLength") || 0;
            let runningChainLength = 0;
            let seenChainInScrape = false;
            let scrapedGoatId = null;

            for (let g = 0; g < allGroups.length; g++) {
                const group = allGroups[g];

                if (group.type === "CHAIN") {
                    seenChainInScrape = true;
                    const uSet = new Set();
                    for (let i = 0; i < group.messages.length; i++) {
                        const hMsg = group.messages[i];
                        const hAuthorId = hMsg.author.id;
                        const hUsername = this.getUsername(hMsg);

                        // Skip duplicate users within the same chain (matches live handler dedup)
                        if (uSet.has(hAuthorId)) continue;
                        uSet.add(hAuthorId);

                        if (BigInt(hMsg.id) > BigInt(lastXp)) {
                            const isChainStarter = (uSet.size === 1);
                            let xpToAward = isChainStarter ? 100 : 25;
                            let isCheater = false;

                            // Anti-cheat: chain breaker starting the next chain
                            if (isChainStarter && scrapedGoatId && hAuthorId === scrapedGoatId) {
                                isCheater = true;
                                this.awardPunishment(hAuthorId, hUsername, 50);
                                xpToAward = 0;
                            }

                            if (!this.stankboard[hAuthorId]?.hasPostedSticker && !isCheater) {
                                xpToAward += 50;
                            }

                            if (xpToAward > 0) {
                                this.awardXp(hAuthorId, hUsername, xpToAward);
                            }
                            this.stankboard[hAuthorId].hasPostedSticker = true;

                            if (BigInt(hMsg.id) > BigInt(highestXpInBatch)) highestXpInBatch = hMsg.id;
                            trackingUpdated = true;
                        }
                    }
                    runningChainLength = uSet.size;

                } else if (group.type === "GAP") {
                    // Only punish if a CHAIN was seen before this GAP in this scrape.
                    if (!seenChainInScrape) {
                        continue;
                    }

                    lastBrokenLengthTracker = runningChainLength;
                    scrapedGoatId = group.messages[0]?.author?.id || null;

                    for (let i = 0; i < group.messages.length; i++) {
                        const chatMsg = group.messages[i];

                        if (BigInt(chatMsg.id) > BigInt(lastPunished)) {
                            const chatUsername = this.getUsername(chatMsg);

                            let penalty = (i === 0) ? (3 * lastBrokenLengthTracker) : (1 * lastBrokenLengthTracker);

                            this.awardPunishment(chatMsg.author.id, chatUsername, penalty);

                            if (BigInt(chatMsg.id) > BigInt(highestPunishedInBatch)) highestPunishedInBatch = chatMsg.id;
                            trackingUpdated = true;
                        }
                    }
                }
            }

            const latestGroup = allGroups[allGroups.length - 1];
            if (latestGroup.type === "CHAIN") {
                const uniqueUsers = new Set();
                latestGroup.messages.forEach(m => uniqueUsers.add(m.author.id));
                this.chainUniqueUsers = Array.from(uniqueUsers);
                this.ongoingChain = this.chainUniqueUsers.length;

                const recentGap = allGroups.slice().reverse().find(g => g.type === "GAP");
                if (recentGap && recentGap.messages.length > 0) {
                    this.newGoatId = recentGap.messages[0].author.id;
                    BdApi.Data.save("StankBot", "newGoatId", this.newGoatId);
                }

                // Anti-cheat: don't grant slayer title to the chain breaker
                const chainStarterId = latestGroup.messages[0].author.id;
                if (this.newGoatId && chainStarterId === this.newGoatId) {
                    // Cheater started this chain â€” find the first legitimate contributor as slayer
                    const realSlayer = latestGroup.messages.find(m => m.author.id !== chainStarterId);
                    if (realSlayer) {
                        this.newSlayerId = realSlayer.author.id;
                        BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                    }
                } else {
                    this.newSlayerId = chainStarterId;
                    BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                }
            } else {
                this.chainUniqueUsers = [];
                this.ongoingChain = 0;
                this.newGoatId = latestGroup.messages[0].author.id;
                BdApi.Data.save("StankBot", "newGoatId", this.newGoatId);

                const recentChain = allGroups.slice().reverse().find(g => g.type === "CHAIN");
                if (recentChain && recentChain.messages.length > 0) {
                    this.newSlayerId = recentChain.messages[0].author.id;
                    BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                }
            }

            if (this.ongoingChain > this.recordChain) {
                this.recordChain = this.ongoingChain;
                BdApi.Data.save("StankBot", "recordChain", this.recordChain);
                trackingUpdated = true;
            }

            this.lastBrokenChainLength = lastBrokenLengthTracker;

            if (trackingUpdated) {
                BdApi.Data.save("StankBot", "lastXpMessageId", highestXpInBatch);
                BdApi.Data.save("StankBot", "lastPunishedMessageId", highestPunishedInBatch);
                BdApi.Data.save("StankBot", "stankboard", this.stankboard);
            }
            BdApi.Data.save("StankBot", "lastBrokenChainLength", this.lastBrokenChainLength);

            this.toast(`Synced! Chain: ${this.ongoingChain}`, false, 8000);
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

    sendCheaterMessage(userId, username, targetChannelId = null) {
        const cheaterTmpl = (this.settings.cheaterTemplate || "").trim();
        if (!cheaterTmpl) return;
        const displayName = (userId === this.BOT_OWNER_ID) ? this.cleanBotOwnerNick() : username;
        const message = cheaterTmpl.replace(/{username}/g, displayName);
        if (targetChannelId) {
            this.sendBotReply(targetChannelId, this.CHEATER_CAUGHT_GIF);
            this.sendBotReply(targetChannelId, message);
        } else {
            const channels = (this.settings.announcementChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean);
            for (const ch of channels) {
                this.sendBotReply(ch, this.CHEATER_CAUGHT_GIF);
                this.sendBotReply(ch, message);
            }
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
        if (this.newSlayerId && this.stankboard[this.newSlayerId]) {
            slayerName = this.stankboard[this.newSlayerId].username;
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
- 100 SP: new Stank chain starter - the new **Slayer**
-  50 SP: first Stank chain contribution (new player)
-  25 SP: valid Stank sticker contribution (once per user per chain)
-   5 SP: Stank emoji reaction on Stank sticker

## Punishment Points
- 3x chain length: chain breaker - the new **Goat**
- 1x chain length: chatting or posting a non-Stank
-         50 flat: breaking the chain then starting the next one (cheating!)
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
        // Discord API requires custom emojis as Name:ID perfectly URL encoded for reactions
        const emojiUri = encodeURIComponent("Stank:1487854129349922816");
        try {
            await BdApi.Net.fetch(`https://discord.com/api/v9/channels/${channelId}/messages/${messageId}/reactions/${emojiUri}/@me`, {
                method: "PUT",
                headers: { "Authorization": token }
            });
            // Cancel the +5 SP that will be auto-awarded to us for our own reaction
            const me = this.UserStore?.getCurrentUser();
            if (me && this.stankboard[me.id]) {
                this.stankboard[me.id].xp = Math.max(0, (this.stankboard[me.id].xp || 0) - 5);
                BdApi.Data.save("StankBot", "stankboard", this.stankboard);
            }
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
                const userId = event.userId;
                const GuildMemberStore = BdApi.Webpack.getStore("GuildMemberStore");
                const memberInfo = GuildMemberStore ? GuildMemberStore.getMember(this.MAPHRA_GUILD_ID, userId) : null;
                const user = this.UserStore?.getUser(userId);
                const username = memberInfo?.nick || user?.globalName || user?.username || "Unknown";
                this.awardXp(userId, username, 5);
                this.toast(`+5 SP -> ${username} (reaction)`);
            }
        } catch (e) {
            this.toast(`Reaction error: ${e.message}`, true);
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

            const recentlyPosted = this.chainUniqueUsers.includes(authorId);
            const username = this.getUsername(msg);

            if (recentlyPosted) {

                // Still react with Stank! User requested repeating stickers get bot reaction
                this.addStankReaction(msg.channel_id, msg.id);
                return;
            } else {
                this.ongoingChain += 1;
                this.toast(`Chain +1 -> ${this.ongoingChain}`);

                this.addStankReaction(msg.channel_id, msg.id);
                this.chainUniqueUsers.push(authorId);

                // XP Math 
                const isFirstEver = !(this.stankboard[authorId] && this.stankboard[authorId].hasPostedSticker);
                let xpToAward = 25;
                let isCheater = false;

                if (this.ongoingChain === 1) {
                    // Anti-cheat: if the chain breaker immediately starts the next chain
                    if (this.newGoatId && authorId === this.newGoatId) {
                        isCheater = true;
                        this.lastChainWasCheaterStart = true;
                        BdApi.Data.save("StankBot", "lastChainWasCheaterStart", true);
                        this.awardPunishment(authorId, username, 50);
                        this.toast(`ðŸš¨ Cheater detected! ${username} +50 punishment`);
                        this.sendCheaterMessage(authorId, username);
                        // Clear slayer â€” next legitimate contributor inherits the title
                        this.newSlayerId = null;
                        BdApi.Data.save("StankBot", "newSlayerId", null);
                        xpToAward = 0;
                    } else {
                        xpToAward = 100;
                        this.newSlayerId = authorId;
                        BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                        this.lastChainWasCheaterStart = false;
                        BdApi.Data.save("StankBot", "lastChainWasCheaterStart", false);
                    }
                }

                // First legitimate contributor after a cheater inherits slayer title + chain starter bonus
                if (!isCheater && this.lastChainWasCheaterStart) {
                    xpToAward = 100;
                    this.newSlayerId = authorId;
                    BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                    this.lastChainWasCheaterStart = false;
                    BdApi.Data.save("StankBot", "lastChainWasCheaterStart", false);
                    this.toast("Chain starter bonus transferred from cheater!");
                }

                if (isFirstEver && !isCheater) {
                    xpToAward += 50;
                }

                if (xpToAward > 0) {
                    this.awardXp(authorId, username, xpToAward);
                    this.toast(`+${xpToAward} SP -> ${username}${isFirstEver ? ' (first sticker!)' : ''}`);
                }
                if (this.stankboard[authorId]) {
                    this.stankboard[authorId].hasPostedSticker = true;
                    BdApi.Data.save("StankBot", "stankboard", this.stankboard);
                }
                BdApi.Data.save("StankBot", "lastXpMessageId", msg.id);

                stateChanged = true;
            }
        } else {
            const authorId = msg.author?.id;
            const username = msg.member?.nick || msg.author?.global_name || msg.author?.username || "Unknown";

            if (this.ongoingChain > 0 || this.chainUniqueUsers.length > 0) {
                this.toast(`ðŸ’¥ Chain shattered at ${this.ongoingChain} by ${username}`);


                // Punish Chain Breaker
                this.newGoatId = authorId;
                BdApi.Data.save("StankBot", "newGoatId", this.newGoatId);
                this.lastBrokenChainLength = this.ongoingChain;
                BdApi.Data.save("StankBot", "lastBrokenChainLength", this.lastBrokenChainLength);

                if (authorId) {
                    const penalty = 3 * this.lastBrokenChainLength;
                    this.awardPunishment(authorId, username, penalty);
                    this.toast(`${username} broke the chain -> +${penalty} punishment`);
                    BdApi.Data.save("StankBot", "lastPunishedMessageId", msg.id);
                }

                if (this.ongoingChain > this.recordChain) {
                    this.recordChain = this.ongoingChain;
                    if ((this.settings.recordTemplate || "").trim()) {
                        this.toast(`ðŸŽ‰ New record! Announcing...`);
                        const announcement = this.getRecordAnnouncementTemplate();
                        const channels = (this.settings.announcementChannelIds || "").split("\n").map(s => s.trim()).filter(Boolean);
                        for (const ch of channels) {
                            this.sendBotReply(ch, announcement);
                        }
                    } else {
                        this.toast(`ðŸŽ‰ New record! (no announcement template)`);
                    }
                }

                this.ongoingChain = 0;
                this.chainUniqueUsers = [];
                stateChanged = true;
            } else {
                // ALREADY BROKEN CHAIN, CHATTING PUNISHMENT
                if (authorId) {
                    const penalty = 1 * this.lastBrokenChainLength;
                    if (penalty > 0) {
                        this.awardPunishment(authorId, username, penalty);
                        this.toast(`${username} chatting penalty -> +${penalty} punishment`);
                        BdApi.Data.save("StankBot", "lastPunishedMessageId", msg.id);
                    }
                }
            }
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
            match("!stank-record-test") || match("!stank-cheater-test")) return;

        let isBoardCommand = match("!stank-board");
        let isXpCommand = rawContent === "!stank-points" || rawContent.startsWith("!stank-points ");
        let isHelpCommand = match("!stank-help");

        if (!isBoardCommand && !isXpCommand && !isHelpCommand) return;

        const isDM = !msg.guild_id;
        const isAllowlisted = this.isChannelAllowed(msg.channel_id, isHelpCommand);

        let shootReply = false;
        if (isDM || isAllowlisted) {
            shootReply = true;
        }

        if (shootReply) {
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
            "Channel IDs for record-broken and cheater-caught announcements (one per line).",
            (val) => {
                this.settings.announcementChannelIds = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Announcement channels updated!");
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

        const defaultBoardTemplate = "# Stank Rankings (top {stankRowsLimit})\nlast slayer: {slayerRank}, {slayerName}, {slayerSP} SP\nlast goat: {goatRank}, {goatName}, {goatSP} PP\n\n{stankRankingsTable}";

        this._addTextarea(sTemplates, "Leaderboard layout ({stankBoard})",
            this.settings.boardLayoutTemplate || defaultBoardTemplate, "140px",
            "Layout for {stankBoard}. Vars: {record}, {ongoing}, {stankRowsLimit}, {slayerRank}, {slayerName}, {slayerSP}, {goatRank}, {goatName}, {goatSP}, {stankRankingsTable}",
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

        this._addTextarea(sTemplates, "Cheater caught announcement",
            this.settings.cheaterTemplate || "", "55px",
            "Text sent after the GIF. Leave empty to disable. Vars: {username}",
            (val) => {
                this.settings.cheaterTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Cheater Announcement Template Saved!");
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

