/**
 * @name StankBot
 * @author randowned
 * @description Maphra community #altar management bot.
 * @version 2.0.0
 */

module.exports = class StankBot {
    toast(msg, isError = false, timeout = 5000) {
        const type = isError ? "error" : "info";
        const bdUI = BdApi?.UI || BdApi;
        if (bdUI && bdUI.showToast) {
            bdUI.showToast(msg, { type: type, timeout: timeout });
        }
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

            this.toast("Booting plugin...", false);
            this.MAPHRA_GUILD_ID = "1482266782306799646";
            this.MEMES_CHANNEL_ID = "1483628334490587336";
            this.DEV_THREAD_ID = "1493190417703895051";
            this.WORSHIP_CHANNEL_ID = "1489889364392546375";
            this.STANK_EMOJI = "<a:Stank:1487854129349922816>";
            this.CHEATER_CAUGHT_GIF = "https://tenor.com/view/bh187-austin-powers-spotlight-search-light-busted-gif-19285562";
            this.BOT_OWNER_ID = "129508601730564096";

            this.UserStore = BdApi.Webpack.getStore("UserStore");
            this.MessageActions = BdApi.Webpack.getModule(m => m && typeof m.sendMessage === "function" && typeof m.editMessage === "function", { searchExports: true });
            this.Dispatcher = BdApi.Webpack.getModule(m => m && typeof m.dispatch === "function" && typeof m.subscribe === "function", { searchExports: true });
            this.ChannelStore = BdApi.Webpack.getStore("ChannelStore");
            this.AuthStore = BdApi.Webpack.getStore("AuthenticationStore");

            // Load Settings
            this.defaultTemplate = "```\n{stankBoard}\n```";
            this.defaultBioTemplate = "Current :Stank: record: {record}\nOngoing :Stank: chain: {ongoing}";
            const savedSettings = BdApi.Data.load("StankBot", "settings") || {};
            this.settings = Object.assign({
                exactCommandMatch: true,
                enableMemesReplies: true,
                enableBoardInMemes: true,
                enableNicknameSync: true,
                enableRecordAnnouncement: true,
                nicknameTemplate: "Randowned ({ongoing}/{record})",
                recordTemplate: "```\nnew record chain: {record}\n\n{stankBoard}\n```",
                scoreTemplate: this.defaultTemplate,
                bioTemplate: this.defaultBioTemplate
            }, savedSettings);

            // Force update user templates to the strict new specification
            this.settings.recordTemplate = "```\nnew record chain: {record}\n\n{stankBoard}\n```";
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

            // Wait for the Bio to sync before we ever listen to a single chat message
            const bioDataLoaded = await this.fetchInitialBio();

            if (!bioDataLoaded) {
                // The rule: Do not start the hooks and just end.
                this.toast("Critical Error: Failed to fetch exact scores from Bio! Plugin aborting startup.", true, 10000);
                return;
            }

            // Next, heavily synchronize the active full set natively from the maphra-worship history deeply
            await this.syncOngoingChainFromHistory();

            // Synchronize the server nickname on startup!
            this.updateNickname();

            // ONLY activate the plugin listeners if the Bio and History data were successfully synced and confirmed
            this.onMessageCreate = this.onMessageCreate.bind(this);
            this.onMessageReactionAdd = this.onMessageReactionAdd.bind(this);
            if (this.Dispatcher) {
                this.Dispatcher.subscribe("MESSAGE_CREATE", this.onMessageCreate);
                this.Dispatcher.subscribe("MESSAGE_REACTION_ADD", this.onMessageReactionAdd);
                this.toast("Dispatcher hooked securely!", false, 10000);
            } else {
                this.toast("Hook failed: Dispatcher not found!", true, 10000);
            }

            BdApi.Patcher.before("StankBot", this.MessageActions, "sendMessage", (thisObject, args) => {
                const [channelId, message] = args;
                if (message && message.content) {
                    const text = message.content.trim();
                    if (text === "!stank-board" || text === "/stank-board") {
                        this.toast(`Intercepted ${text}!`);
                        message.content = this.getScoreTemplate();
                    } else if (text === "!stank-record-test" || text === "/stank-record-test") {
                        this.toast(`Intercepted template test!`);
                        message.content = this.getRecordAnnouncementTemplate();
                    } else if (text === "!stank-help" || text === "/stank-help") {
                        this.toast(`Intercepted ${text}!`);
                        message.content = this.getHelpTemplate();
                    } else if (text === "!stank-points" || text === "/stank-points") {
                        this.toast(`Intercepted ${text}!`);
                        const me = this.UserStore.getCurrentUser();
                        if (me) {
                            const xp = (this.stankboard[me.id] && this.stankboard[me.id].xp) || 0;
                            const pun = (this.stankboard[me.id] && this.stankboard[me.id].punishments) || 0;
                            const stankSorted = Object.entries(this.stankboard).map(([id, u]) => ({ id, ...u })).sort((a, b) => b.xp - a.xp);
                            const punSorted = Object.entries(this.stankboard).map(([id, u]) => ({ id, ...u })).filter(u => (u.punishments || 0) > 0).sort((a, b) => (b.punishments || 0) - (a.punishments || 0));
                            const stankRank = stankSorted.findIndex(u => u.id === me.id);
                            const punRank = punSorted.findIndex(u => u.id === me.id);
                            const stankRankStr = stankRank !== -1 ? (stankRank + 1) : "N/A";
                            const punRankStr = punRank !== -1 ? (punRank + 1) : "N/A";
                            message.content = `\`\`\`\nstank points: ${Number(xp).toLocaleString()}, rank: ${stankRankStr}\npunishment points: ${Number(pun).toLocaleString()}, rank: ${punRankStr}\n\`\`\``;
                        }
                    } else if (text === "!stank-cheater-test" || text === "/stank-cheater-test") {
                        this.toast(`Intercepted ${text}!`);
                        const testUser = this.UserStore?.getCurrentUser();
                        const memberStore = BdApi.Webpack.getStore("GuildMemberStore");
                        const memberInfo = testUser && memberStore ? memberStore.getMember(this.MAPHRA_GUILD_ID, testUser.id) : null;
                        const myName = memberInfo?.nick || testUser?.globalName || testUser?.username || "Unknown";
                        this.sendCheaterMessage(channelId, testUser?.id, myName);
                        message.content = "!stank-cheater-test";
                    } else if (text === "!stank-board-reset" || text === "/stank-board-reset") {
                        this.toast(`Intercepted ${text}!`);
                        this.resetBoard();
                        message.content = `\`\`\`\nboard reset\n\n${this.generateStankBoardAscii()}\n\`\`\``;
                    } else if (text === "!stank-board-reload" || text === "/stank-board-reload") {
                        this.toast(`Intercepted ${text}!`);
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
        const defaultBoardTemplate = "chain record: {record}\nongoing chain: {ongoing}\n\n# Stank Rankings (top {stankRowsLimit})\nnew slayer: {slayerRank}, {slayerName}, {slayerXp} Stank Points\n{stankRankingsTable}\n\n# Punishment Rankings (top {punishRowsLimit})\nnew goat: {goatRank}, {goatName}, {goatPunish} Punishment Points\n{punishmentRankingsTable}";
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
        const punishRowsLimit = parseInt(this.settings.punishmentRankingRows, 10) || 5;

        const stankArr = Object.entries(this.stankboard).map(([id, u]) => ({ id, ...u })).sort((a, b) => b.xp - a.xp);

        let slayerName = "Unknown";
        let slayerRank = "N/A";
        let slayerXp = 0;
        if (this.newSlayerId && this.stankboard[this.newSlayerId]) {
            slayerName = this.stankboard[this.newSlayerId].username;
            const idx = stankArr.findIndex(u => u.id === this.newSlayerId);
            if (idx !== -1) { slayerRank = idx + 1; slayerXp = stankArr[idx].xp; }
        }

        const punishArr = Object.entries(this.stankboard)
            .map(([id, u]) => ({ id, ...u }))
            .filter(u => (u.punishments || 0) > 0)
            .sort((a, b) => (b.punishments || 0) - (a.punishments || 0));

        let goatName = "None";
        let goatRank = "N/A";
        let goatPunish = 0;
        if (this.newGoatId && this.stankboard[this.newGoatId]) {
            goatName = this.stankboard[this.newGoatId].username;
            const idx = punishArr.findIndex(u => u.id === this.newGoatId);
            if (idx !== -1) { goatRank = idx + 1; goatPunish = punishArr[idx].punishments || 0; }
        }

        tmpl = this.applyCommonReplacements(tmpl);
        tmpl = tmpl.replace(/{stankRowsLimit}/g, stankRowsLimit);
        tmpl = tmpl.replace(/{slayerRank}/g, slayerRank);
        tmpl = tmpl.replace(/{slayerName}/g, slayerName);
        tmpl = tmpl.replace(/{slayerXp}/g, Number(slayerXp).toLocaleString());
        tmpl = tmpl.replace(/{punishRowsLimit}/g, punishRowsLimit);
        tmpl = tmpl.replace(/{goatRank}/g, goatRank);
        tmpl = tmpl.replace(/{goatName}/g, goatName);
        tmpl = tmpl.replace(/{goatPunish}/g, Number(goatPunish).toLocaleString());

        // Stank Table
        let stankTableStr = "";
        const stankTopN = stankArr.slice(0, stankRowsLimit);
        for (let i = 0; i < stankTopN.length; i++) {
            const rank = (i + 1).toString().padEnd(3, " ");
            const user = (stankTopN[i].username || "Unknown").substring(0, 20).padEnd(20, " ");
            const xp = Number(stankTopN[i].xp).toLocaleString();
            stankTableStr += `${rank} | ${user} | ${xp} Stank Points\n`;
        }
        if (stankTopN.length === 0) stankTableStr += "No records yet.\n";
        // Trim trailing newline securely
        tmpl = tmpl.replace(/{stankRankingsTable}/g, stankTableStr.replace(/\n$/, ""));

        // Punishment Table
        let punishTableStr = "";
        const punTopN = punishArr.slice(0, punishRowsLimit);
        for (let i = 0; i < punTopN.length; i++) {
            const rank = (i + 1).toString().padEnd(3, " ");
            const user = (punTopN[i].username || "Unknown").substring(0, 20).padEnd(20, " ");
            const pun = Number(punTopN[i].punishments || 0).toLocaleString();
            punishTableStr += `${rank} | ${user} | ${pun} Punishment Points\n`;
        }
        if (punTopN.length === 0) punishTableStr += "No records yet.\n";
        tmpl = tmpl.replace(/{punishmentRankingsTable}/g, punishTableStr.replace(/\n$/, ""));

        return tmpl;
    }

    async syncOngoingChainFromHistory() {
        try {
            this.toast("Initializing Deep Historical Group Matrix...");
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
                let fetchUrl = `https://discord.com/api/v9/channels/${this.WORSHIP_CHANNEL_ID}/messages?limit=100`;
                if (lastMessageId) fetchUrl += `&before=${lastMessageId}`;

                const res = await BdApi.Net.fetch(fetchUrl, { headers: { "Authorization": token } });
                if (!res.ok) {
                    this.toast("Failed to parse history.", true);
                    this.toast(`History parse error: ${await res.text()}`, true);
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
                    // Cheater started this chain — find the first legitimate contributor as slayer
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

            this.toast(`Offline Matrix Scrape complete! Booted with Stank: ${this.ongoingChain}. Loaded successfully.`, false, 8000);
            return true;
        } catch (e) {
            this.toast(`Network error syncing deep group trace: ${e.toString()}`, true);
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
        this.toast("Stopping Plugin...");
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

        this.toast(`Syncing Nickname...`);
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

    sendCheaterMessage(channelId, userId, username) {
        const displayName = (userId === this.BOT_OWNER_ID) ? this.cleanBotOwnerNick() : username;
        this.sendBotReply(channelId, this.CHEATER_CAUGHT_GIF);
        this.sendBotReply(channelId, `${displayName} - penalty! - 50 punishment points awarded!`);
    }

    getScoreTemplate() {
        let tmpl = this.applyCommonReplacements(this.settings.scoreTemplate || this.defaultTemplate);
        tmpl = tmpl.replace(/{stankBoard}/g, this.generateStankBoardAscii());
        return tmpl;
    }

    getBioTemplate() {
        return this.applyCommonReplacements(this.settings.bioTemplate || this.defaultBioTemplate);
    }

    getRecordAnnouncementTemplate(isMemes = false) {
        let tmpl = this.applyCommonReplacements(this.settings.recordTemplate || "```\nnew record chain: {record}\n\n{stankBoard}\n```");

        let slayerName = "Unknown";
        if (this.newSlayerId && this.stankboard[this.newSlayerId]) {
            slayerName = this.stankboard[this.newSlayerId].username;
        }
        tmpl = tmpl.replace(/{chainStarterServerNickname}/g, slayerName);

        if (isMemes && !this.settings.enableBoardInMemes) {
            tmpl = tmpl.replace(/\n*\{stankBoard\}\n*/g, "\n");
        } else {
            tmpl = tmpl.replace(/{stankBoard}/g, this.generateStankBoardAscii());
        }

        return tmpl;
    }

    getHelpTemplate() {
        return `\`\`\`markdown
# StankBot

# Commands
!stank-board - the leaderboard
!stank-points - user's Stank and Punishment points
!stank-help - this help message

# Stank Points
- 100 SP new Stank chain starter - the new slayer
-  50 SP first Stank chain contribution
-  25 SP valid Stank sticker contribution
-   5 SP Stank emoji reaction on Stank sticker

# Punishment Points
- 3x chain length: chain breaker - the new goat
- 1x chain length: chatting or posting a non-Stank
- 50 flat: breaking the chain then starting the next one (cheating!)
\`\`\``;
    }

    updateBio() {
        const bioContent = `${this.getBioTemplate()}\n\nyt@randowned\nu/randowned`;
        this.toast(`Syncing new scores to Bio...`);
        const token = this.getToken();
        BdApi.Net.fetch(`https://discord.com/api/v9/guilds/${this.MAPHRA_GUILD_ID}/profile/@me`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "Authorization": token
            },
            body: JSON.stringify({ bio: bioContent })
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

            if (res.ok) {
                this.toast(`Auto-reply transmitted!`);
            } else {
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
        } catch (e) {
            this.toast(`Failed to react: ${e.toString()}`, true);
        }
    }

    onMessageReactionAdd(event) {
        if (!event) return;
        // Verify it was in the worship channel
        if (event.channelId !== this.WORSHIP_CHANNEL_ID) return;
        // Check if the reaction is the Stank Emoji
        const emojiName = event.emoji?.name?.toLowerCase() || "";
        if (emojiName.includes("stank") || event.emoji?.id === "1487854129349922816") {
            const userId = event.userId;
            const GuildMemberStore = BdApi.Webpack.getStore("GuildMemberStore");
            const memberInfo = GuildMemberStore ? GuildMemberStore.getMember(this.MAPHRA_GUILD_ID, userId) : null;
            const user = this.UserStore?.getUser(userId);
            const username = memberInfo?.nick || user?.globalName || user?.username || "Unknown";
            this.awardXp(userId, username, 5);
            this.toast(`Stank reaction parsed! XP +5 -> ${username}`);
        }
    }

    onMessageCreate(event) {
        if (!event || !event.message) return;
        const msg = event.message;

        if (msg.channel_id === this.WORSHIP_CHANNEL_ID) {
            this.processWorshipMessage(msg);
        }

        this.processCommands(msg);
    }

    processWorshipMessage(msg) {
        const isStank = this.isStankMessage(msg);
        this.toast(`Worship msg read! isStank: ${isStank}`);

        let stateChanged = false;

        if (isStank) {
            const authorId = msg.author?.id;
            if (!authorId) return;

            const recentlyPosted = this.chainUniqueUsers.includes(authorId);
            const username = this.getUsername(msg);

            if (recentlyPosted) {
                this.toast(`Ignored repeat Absolute User: ${authorId}`);
                // Still react with Stank! User requested repeating stickers get bot reaction
                this.addStankReaction(msg.channel_id, msg.id);
                return;
            } else {
                this.ongoingChain += 1;
                this.toast(`Valid Stank added! New Absolute Chain: ${this.ongoingChain}`);

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
                        this.awardPunishment(authorId, username, 50);
                        this.toast(`🚨 CHEATER CAUGHT! ${username} broke the chain and tried to start a new one! +50 Punishment`);
                        this.sendCheaterMessage(this.MEMES_CHANNEL_ID, authorId, username);
                        // Clear slayer — next legitimate contributor inherits the title
                        this.newSlayerId = null;
                        BdApi.Data.save("StankBot", "newSlayerId", null);
                        xpToAward = 0;
                    } else {
                        xpToAward = 100;
                        this.newSlayerId = authorId;
                        BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                    }
                }

                // First legitimate contributor after a cheater inherits slayer title
                if (!isCheater && this.newSlayerId === null) {
                    this.newSlayerId = authorId;
                    BdApi.Data.save("StankBot", "newSlayerId", this.newSlayerId);
                }

                if (isFirstEver && !isCheater) {
                    xpToAward += 50;
                }

                if (xpToAward > 0) {
                    this.awardXp(authorId, username, xpToAward);
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
                this.toast(`Non-stank message shattered chain!`);

                // Punish Chain Breaker
                this.newGoatId = authorId;
                BdApi.Data.save("StankBot", "newGoatId", this.newGoatId);
                this.lastBrokenChainLength = this.ongoingChain;
                BdApi.Data.save("StankBot", "lastBrokenChainLength", this.lastBrokenChainLength);

                if (authorId) {
                    const penalty = 3 * this.lastBrokenChainLength;
                    this.awardPunishment(authorId, username, penalty);
                    this.toast(`Chain Breaker Penalty! ${username} +${penalty} Punishments`);
                    BdApi.Data.save("StankBot", "lastPunishedMessageId", msg.id);
                }

                if (this.ongoingChain > this.recordChain) {
                    this.recordChain = this.ongoingChain;
                    if (this.settings.enableRecordAnnouncement) {
                        this.toast(`🎉 FINALIZED RECORD RUN BROKEN! Sending to #memes...`);
                        this.sendBotReply(this.MEMES_CHANNEL_ID, this.getRecordAnnouncementTemplate(true));
                    } else {
                        this.toast(`🎉 FINALIZED RECORD RUN BROKEN! (announcement disabled)`);
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
                        this.toast(`Chatting Penalty! ${username} +${penalty} Punishments`);
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

        // Admin commands — silently ignore from non-admin users
        if (match("!stank-board-reset") || match("!stank-board-reload") ||
            match("!stank-record-test") || match("!stank-cheater-test")) return;

        let isBoardCommand = match("!stank-board");
        let isXpCommand = match("!stank-points");
        let isHelpCommand = match("!stank-help");

        if (!isBoardCommand && !isXpCommand && !isHelpCommand) return;

        this.toast(`Incoming command detected!`);

        // Native check: Direct Messages and Group Chats do not have a guildId attached to the payload
        const isDM = !msg.guild_id;
        const inMemes = msg.channel_id === this.MEMES_CHANNEL_ID;
        const inDevThread = msg.channel_id === this.DEV_THREAD_ID;

        let shootReply = false;
        if (isDM) {
            this.toast(`Routing auto-reply to DM!`);
            shootReply = true;
        } else if (inDevThread) {
            this.toast(`Routing auto-reply to isolated DEV thread!`);
            shootReply = true;
        } else if (inMemes) {
            if (this.settings.enableMemesReplies) {
                if ((isBoardCommand || isXpCommand) && !this.settings.enableBoardInMemes) {
                    this.toast(`Ignored stank tracking command in #memes due to settings!`);
                } else {
                    this.toast(`Routing auto-reply to #memes!`);
                    shootReply = true;
                }
            } else {
                this.toast(`Ignored command: #memes auto-reply disabled!`);
            }
        }

        if (shootReply) {
            if (isXpCommand) {
                const totalXp = (this.stankboard[msg.author.id] && this.stankboard[msg.author.id].xp) || 0;
                const totalPunish = (this.stankboard[msg.author.id] && this.stankboard[msg.author.id].punishments) || 0;
                const xpStr = Number(totalXp).toLocaleString();
                const punStr = Number(totalPunish).toLocaleString();
                const stankSorted = Object.entries(this.stankboard).map(([id, u]) => ({ id, ...u })).sort((a, b) => b.xp - a.xp);
                const punSorted = Object.entries(this.stankboard).map(([id, u]) => ({ id, ...u })).filter(u => (u.punishments || 0) > 0).sort((a, b) => (b.punishments || 0) - (a.punishments || 0));
                const stankRank = stankSorted.findIndex(u => u.id === msg.author.id);
                const punRank = punSorted.findIndex(u => u.id === msg.author.id);
                const stankRankStr = stankRank !== -1 ? (stankRank + 1) : "N/A";
                const punRankStr = punRank !== -1 ? (punRank + 1) : "N/A";
                const replyText = `\`\`\`\nstank points: ${xpStr}, rank: ${stankRankStr}\npunishment points: ${punStr}, rank: ${punRankStr}\n\`\`\``;
                this.sendBotReply(msg.channel_id, replyText, msg.id);
            } else if (isBoardCommand) {
                this.sendBotReply(msg.channel_id, this.getScoreTemplate());
            } else if (isHelpCommand) {
                this.sendBotReply(msg.channel_id, this.getHelpTemplate(), msg.id);
            }
        }
    }

    // ─── Settings Panel Factory Helpers ───

    _addNote(parent, text, marginBottom = "20px") {
        const note = document.createElement("div");
        Object.assign(note.style, { marginTop: "8px", marginBottom, fontSize: "14px", color: "var(--text-muted)" });
        note.innerText = text;
        parent.appendChild(note);
    }

    _addCheckbox(parent, label, settingKey, note, onChange) {
        const container = document.createElement("label");
        Object.assign(container.style, { display: "flex", alignItems: "center", gap: "10px", fontSize: "16px", cursor: "pointer" });

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = this.settings[settingKey];
        Object.assign(checkbox.style, { width: "20px", height: "20px", cursor: "pointer" });

        checkbox.addEventListener("change", (e) => {
            this.settings[settingKey] = e.target.checked;
            BdApi.Data.save("StankBot", "settings", this.settings);
            this.toast(`${label}: ${e.target.checked ? "ON" : "OFF"}`);
            if (onChange) onChange(e.target.checked);
        });

        container.appendChild(checkbox);
        container.appendChild(document.createTextNode(label));
        parent.appendChild(container);
        this._addNote(parent, note);
    }

    _addTextarea(parent, label, value, height, note, onChange) {
        const container = document.createElement("label");
        Object.assign(container.style, { display: "flex", flexDirection: "column", gap: "10px", fontSize: "16px" });
        container.appendChild(document.createTextNode(label));

        const textarea = document.createElement("textarea");
        textarea.value = value;
        Object.assign(textarea.style, {
            width: "100%", height: height, fontFamily: "monospace", padding: "10px",
            backgroundColor: "rgba(0, 0, 0, 0.4)", color: "var(--text-normal)",
            border: "1px solid rgba(255, 255, 255, 0.15)", borderRadius: "4px", resize: "vertical"
        });
        textarea.addEventListener("change", (e) => onChange(e.target.value.trim(), e));

        container.appendChild(textarea);
        parent.appendChild(container);
        this._addNote(parent, note, "25px");
    }

    _addNumberInput(parent, label, settingKey, defaultVal) {
        const container = document.createElement("label");
        Object.assign(container.style, { display: "flex", alignItems: "center", gap: "10px", fontSize: "16px", marginBottom: "8px" });
        container.appendChild(document.createTextNode(label));

        const input = document.createElement("input");
        input.type = "number";
        input.min = "1";
        input.max = "100";
        input.value = this.settings[settingKey] || defaultVal;
        Object.assign(input.style, {
            width: "60px", padding: "4px",
            backgroundColor: "rgba(0, 0, 0, 0.4)", color: "var(--text-normal)",
            border: "1px solid rgba(255, 255, 255, 0.15)", borderRadius: "4px"
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
        const container = document.createElement("label");
        Object.assign(container.style, { display: "flex", flexDirection: "column", gap: "10px", fontSize: "16px" });
        container.appendChild(document.createTextNode(label));

        const input = document.createElement("input");
        input.type = "text";
        input.value = value;
        Object.assign(input.style, {
            width: "100%", padding: "10px", fontFamily: "monospace",
            backgroundColor: "rgba(0, 0, 0, 0.4)", color: "var(--text-normal)",
            border: "1px solid rgba(255, 255, 255, 0.15)", borderRadius: "4px"
        });
        input.addEventListener("change", (e) => onChange(e.target.value.trim()));

        container.appendChild(input);
        parent.appendChild(container);
        this._addNote(parent, note);
    }

    // ─── Settings Panel ───

    getSettingsPanel() {
        const panel = document.createElement("div");
        panel.style.padding = "20px";
        panel.style.color = "var(--text-normal)";

        const createGroup = (title) => {
            const fieldset = document.createElement("fieldset");
            Object.assign(fieldset.style, { border: "1px solid var(--background-modifier-accent)", borderRadius: "8px", padding: "15px", marginBottom: "25px" });
            const legend = document.createElement("legend");
            Object.assign(legend.style, { padding: "0 8px", fontWeight: "bold", fontSize: "16px", color: "var(--header-primary)" });
            legend.innerText = title;
            fieldset.appendChild(legend);
            return fieldset;
        };

        const groupCore = createGroup("Core Behavior & Triggers");
        const groupTemplates = createGroup("Template Customization");

        // ── Core Checkboxes ──
        this._addCheckbox(groupCore, "Require exact text match for commands", "exactCommandMatch",
            "If checked, '!stank-board' must be the only text in the message to successfully trigger a reply. If unchecked, the bot will wildly reply even if the command keyword is embedded deep inside a longer paragraph.");

        this._addCheckbox(groupCore, "Enable commands auto-reply in #memes channel", "enableMemesReplies",
            "If checked, the bot will visibly reply to user's incoming !stank-board commands inside the #memes channel. If unchecked, it drops them and ONLY processes command tags silently in Direct Messages.");

        this._addCheckbox(groupCore, "Send !stank-board to #memes channel", "enableBoardInMemes",
            "If unchecked, drops !stank-board commands in #memes to reduce spam, and ALSO cleanly omits {stankBoard} injections from the broken chain auto-announcements.");

        this._addCheckbox(groupCore, "Enable Record Broken specific announcements in #memes", "enableRecordAnnouncement",
            "If checked, the bot will autonomously shoot out an announcement natively inside the #memes channel whenever the active chain physically breaks the highest recorded score.");

        this._addCheckbox(groupCore, "Synchronize server nickname with ongoing chain", "enableNicknameSync",
            "If checked, automatically overwrites your Maphra server nickname on initial plugin load and upon every link added or shattered. Unchecking this immediately resets your nickname back to solely 'YourName' via API push.\n*Note: Discord limits all user nickname changes to approximately 10 per hour.*",
            () => this.updateNickname());

        // ── Rows Configuration ──
        this._addNumberInput(groupTemplates, "Stank Rankings Rows: ", "stankRankingRows", 5);
        this._addNumberInput(groupTemplates, "Punishment Rankings Rows: ", "punishmentRankingRows", 5);

        // ── Template Editors ──
        this._addTextarea(groupTemplates, "Discord Profile Bio Layout",
            this.settings.bioTemplate || this.defaultBioTemplate, "60px",
            "Design the layout specifically applied to your personal Discord Bio.\nWARNING: The plugin uses a dynamic RegExp parser under the hood tied strictly to this layout string. If you change this out of sync with your physical profile bio, it aggressively triggers an API push matching this layout immediately to protect data memory sync.",
            (val, e) => {
                if (!val.includes("{record}") || !val.includes("{ongoing}")) {
                    this.toast("Bio template must contain both {record} and {ongoing} for memory reading!", true);
                    e.target.value = this.settings.bioTemplate || this.defaultBioTemplate;
                    return;
                }
                this.settings.bioTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Bio Template Saved!");
                this.updateBio();
            });

        const defaultBoardTemplate = "chain record: {record}\nongoing chain: {ongoing}\n\n# Stank Rankings (top {stankRowsLimit})\nnew slayer: {slayerRank}, {slayerName}, {slayerXp} Stank Points\n{stankRankingsTable}\n\n# Punishment Rankings (top {punishRowsLimit})\nnew goat: {goatRank}, {goatName}, {goatPunish} Punishment Points\n{punishmentRankingsTable}";

        this._addTextarea(groupTemplates, "Internal ASCII {stankBoard} Format",
            this.settings.boardLayoutTemplate || defaultBoardTemplate, "160px",
            "Configures the precise internal table structure that replaces the {stankBoard} variable. Available placeholders: {record}, {ongoing}, {stankRowsLimit}, {slayerRank}, {slayerName}, {slayerXp}, {punishRowsLimit}, {goatRank}, {goatName}, {goatPunish}, :Stank:, {stankRankingsTable}, {punishmentRankingsTable}.",
            (val) => {
                this.settings.boardLayoutTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("StankBoard Format Saved!");
            });

        this._addTextarea(groupTemplates, "Board Auto-Reply Format",
            this.settings.scoreTemplate || this.defaultTemplate, "80px",
            "Design the layout of your Stank Bot replies (`!stank-board`). Available placeholders: {record}, {ongoing}, {stankBoard}, and :Stank:",
            (val) => {
                this.settings.scoreTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Score Template Saved!");
            });

        this._addTextarea(groupTemplates, "Record Announcement Format",
            this.settings.recordTemplate || "```\nnew record chain: {record}\n\n{stankBoard}\n```", "120px",
            "Custom formatting applied globally to Record Broken messages. Available variables: {record}, :Stank:, {chainStarterServerNickname}, {stankBoard}",
            (val) => {
                this.settings.recordTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Announcement Template Saved!");
            });

        this._addTextInput(groupTemplates, "Custom Nickname Format",
            this.settings.nicknameTemplate || "Randowned ({ongoing}/{record})",
            "Custom formatting applied to your Server Nickname if sync is turned on. Available variables: {record}, {ongoing}",
            (val) => {
                this.settings.nicknameTemplate = val;
                BdApi.Data.save("StankBot", "settings", this.settings);
                this.toast("Nickname Template Saved!");
                if (this.settings.enableNicknameSync) this.updateNickname();
            });

        panel.appendChild(groupCore);
        panel.appendChild(groupTemplates);
        return panel;
    }
};

