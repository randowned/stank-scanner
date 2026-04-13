/**
 * @name StankScanner
 * @author randowned
 * @description Listens to #maphra-worship on Maphra Community Discord Server for Stank chains and saves score to Server Bio. !stankscore to print current scores!
 * @version 1.0.0
 */

module.exports = class StankScanner {
    toast(msg, isError = false, timeout = 5000) {
        const type = isError ? "error" : "info";
        const bdUI = BdApi?.UI || BdApi;
        if (bdUI && bdUI.showToast) {
            bdUI.showToast(msg, { type: type, timeout: timeout });
        }
    }

    async start() {
        try {
            // Hijack BetterDiscord's toast container globally to force them to render at the Top Center!
            const bdDOM = BdApi?.DOM || BdApi;
            if (bdDOM && bdDOM.addStyle) {
                bdDOM.addStyle("StankScanner-Toast", `
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

            this.UserStore = BdApi.Webpack.getStore("UserStore");
            this.MessageActions = BdApi.Webpack.getModule(m => m && typeof m.sendMessage === "function" && typeof m.editMessage === "function", { searchExports: true });
            this.Dispatcher = BdApi.Webpack.getModule(m => m && typeof m.dispatch === "function" && typeof m.subscribe === "function", { searchExports: true });
            this.ChannelStore = BdApi.Webpack.getStore("ChannelStore");
            this.AuthStore = BdApi.Webpack.getStore("AuthenticationStore");

            // Load Settings
            this.defaultTemplate = ":Stank: record chain: {record}\n:Stank: ongoing chain: {ongoing}";
            this.settings = Object.assign({
                exactCommandMatch: true,
                enableMemesReplies: true,
                enableNicknameSync: true,
                enableRecordAnnouncement: true,
                nicknameTemplate: "Randowned ({record}/{ongoing})",
                recordTemplate: ":tada: New :Stank: record chain: {record}",
                scoreTemplate: this.defaultTemplate
            }, BdApi.Data.load("StankScanner", "settings") || {});

            // We entirely remove the defaults. They must be fetched from the API.
            this.recordChain = null;
            this.ongoingChain = null;
            this.chainUniqueUsers = [];

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
            if (this.Dispatcher) {
                this.Dispatcher.subscribe("MESSAGE_CREATE", this.onMessageCreate);
                this.toast("Dispatcher hooked securely!", false, 10000);
            } else {
                this.toast("Hook failed: Dispatcher not found!", true, 10000);
            }

            BdApi.Patcher.before("StankScanner", this.MessageActions, "sendMessage", (thisObject, args) => {
                const [channelId, message] = args;
                if (message && message.content) {
                    const text = message.content.trim();
                    if (text === "!stankrecord" || text === "/stankrecord" || text === "!stankscore" || text === "/stankscore") {
                        this.toast(`Intercepted ${text}!`);
                        message.content = this.getScoreTemplate();
                    } else if (text === "!stankrecord-test" || text === "/stankrecord-test") {
                        this.toast(`Intercepted template test!`);
                        message.content = this.getRecordAnnouncementTemplate();
                    }
                }
            });

        } catch (err) {
            const bdUI = BdApi.UI || BdApi;
            if (bdUI && bdUI.alert) {
                bdUI.alert("StankScanner Startup Error", "Failed to start!\n\n" + (err.stack || err.toString()));
            }
        }
    }

    async syncOngoingChainFromHistory() {
        this.toast(`Tracing deep history mathematically natively from #maphra-worship...`);
        const token = this.AuthStore ? this.AuthStore.getToken() : "";

        let lastMessageId = null;
        let rebuiltBuffer = new Set();
        let loopLimit = 10; // Max 1000 messages deep (10 pages) to strictly prevent aggressive anti-spam bot kicks
        let currentLoop = 0;
        let chainBroke = false;

        try {
            while (currentLoop < loopLimit && !chainBroke) {
                currentLoop++;
                let fetchUrl = `https://discord.com/api/v9/channels/${this.WORSHIP_CHANNEL_ID}/messages?limit=100`;
                if (lastMessageId) {
                    fetchUrl += `&before=${lastMessageId}`;
                }

                const res = await BdApi.Net.fetch(fetchUrl, {
                    headers: { "Authorization": token }
                });

                if (!res.ok) {
                    this.toast(`History fetch hit API limit Phase ${currentLoop}! Falling back to Bio. Status: ${res.status}`, true, 10000);
                    break;
                }

                const messages = await res.json();
                if (messages.length === 0) break;

                for (const msg of messages) {
                    const hasNoText = (!msg.content || msg.content.trim() === "");
                    const stickers = msg.stickers || msg.stickerItems || msg.sticker_items || msg.custom_stickers || [];

                    let isStank = false;
                    if (hasNoText && stickers.length === 1) {
                        const stickerName = (stickers[0].name || "").toLowerCase();
                        if (stickerName.includes("stank")) {
                            isStank = true;
                        }
                    }

                    if (isStank) {
                        const authorId = msg.author?.id;
                        if (!authorId) continue;
                        rebuiltBuffer.add(authorId);
                    } else {
                        chainBroke = true;
                        break;
                    }
                }

                lastMessageId = messages[messages.length - 1].id;
            }

            this.chainUniqueUsers = Array.from(rebuiltBuffer);

            if (chainBroke) {
                this.ongoingChain = this.chainUniqueUsers.length;
                this.toast(`Network history traced perfectly! Ongoing Chain natively evaluated at: ${this.ongoingChain}. Bound ${this.ongoingChain} absolute unique users.`, false, 7000);
            } else {
                this.toast(`Hit max history scrape limit. Relying strictly on Bio score: ${this.ongoingChain}. Safely locked ${this.chainUniqueUsers.length} deep users.`, true, 10000);
            }
            return true;
        } catch (e) {
            this.toast(`Network error syncing deep channel trace: ${e.toString()}`, true);
            this.chainUniqueUsers = [];
            return true;
        }
    }

    async fetchInitialBio() {
        try {
            this.toast("Fetching Server Bio data...");
            const token = this.AuthStore ? this.AuthStore.getToken() : "";
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
                let tmpl = this.settings.scoreTemplate || this.defaultTemplate;
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
        }
        BdApi.Patcher.unpatchAll("StankScanner");

        const bdDOM = BdApi?.DOM || BdApi;
        if (bdDOM && bdDOM.removeStyle) {
            bdDOM.removeStyle("StankScanner-Toast");
        }
    }

    async updateNickname() {
        let targetNick = "Randowned";
        if (this.settings.enableNicknameSync) {
            let tmpl = this.settings.nicknameTemplate || "Randowned ({record}/{ongoing})";
            tmpl = tmpl.replace(/{record}/g, this.recordChain !== null ? this.recordChain : 0);
            tmpl = tmpl.replace(/{ongoing}/g, this.ongoingChain !== null ? this.ongoingChain : 0);
            targetNick = tmpl;
        }

        this.toast(`Syncing Nickname...`);
        const token = this.AuthStore ? this.AuthStore.getToken() : "";
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
        let tmpl = this.settings.scoreTemplate || this.defaultTemplate;
        tmpl = tmpl.replace(/{record}/g, this.recordChain !== null ? this.recordChain : 0);
        tmpl = tmpl.replace(/{ongoing}/g, this.ongoingChain !== null ? this.ongoingChain : 0);
        tmpl = tmpl.replace(/:Stank:/g, this.STANK_EMOJI);
        return tmpl;
    }

    getRecordAnnouncementTemplate() {
        let tmpl = this.settings.recordTemplate || ":tada: New :Stank: record chain: {record}";
        tmpl = tmpl.replace(/{record}/g, this.recordChain !== null ? this.recordChain : 0);
        tmpl = tmpl.replace(/:Stank:/g, this.STANK_EMOJI);
        return tmpl;
    }

    updateBio() {
        const bioContent = `${this.getScoreTemplate()}\n\nyt@randowned\nu/randowned`;
        this.toast(`Syncing new scores to Bio...`);
        const token = this.AuthStore ? this.AuthStore.getToken() : "";
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

    async sendBotReply(channelId, textContent) {
        const token = this.AuthStore ? this.AuthStore.getToken() : "";
        try {
            const res = await BdApi.Net.fetch(`https://discord.com/api/v9/channels/${channelId}/messages`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": token
                },
                body: JSON.stringify({ content: textContent })
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
        const token = this.AuthStore ? this.AuthStore.getToken() : "";
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

    onMessageCreate(event) {
        if (!event || !event.message) return;
        const msg = event.message;

        if (msg.channel_id === this.WORSHIP_CHANNEL_ID) {
            this.processWorshipMessage(msg);
        }

        this.processCommands(msg);
    }

    processWorshipMessage(msg) {
        const hasNoText = (!msg.content || msg.content.trim() === "");
        const stickers = msg.stickers || msg.stickerItems || msg.sticker_items || msg.custom_stickers || [];

        let isStank = false;
        if (hasNoText && stickers.length === 1) {
            const stickerName = (stickers[0].name || "").toLowerCase();
            if (stickerName.includes("stank")) {
                isStank = true;
            }
        }

        this.toast(`Worship msg read! isStank: ${isStank}`);

        let stateChanged = false;

        if (isStank) {
            const authorId = msg.author?.id;
            if (!authorId) return;

            const recentlyPosted = this.chainUniqueUsers.includes(authorId);

            if (recentlyPosted) {
                this.toast(`Ignored repeat Absolute User: ${authorId}`);
                return;
            } else {
                this.ongoingChain += 1;
                this.toast(`Valid Stank added! New Absolute Chain: ${this.ongoingChain}`);

                this.addStankReaction(msg.channel_id, msg.id);
                this.chainUniqueUsers.push(authorId);

                stateChanged = true;
            }
        } else {
            if (this.ongoingChain > 0 || this.chainUniqueUsers.length > 0) {
                this.toast(`Non-stank message shattered chain!`);

                if (this.ongoingChain > this.recordChain) {
                    this.recordChain = this.ongoingChain;
                    if (this.settings.enableRecordAnnouncement) {
                        this.toast(`🎉 FINALIZED RECORD RUN BROKEN! Sending to #memes...`);
                        this.sendBotReply(this.MEMES_CHANNEL_ID, this.getRecordAnnouncementTemplate());
                    } else {
                        this.toast(`🎉 FINALIZED RECORD RUN BROKEN! (announcement disabled)`);
                    }
                }

                this.ongoingChain = 0;
                this.chainUniqueUsers = [];
                stateChanged = true;
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

        let isRecordCommand = false;
        let isTestCommand = false;
        if (msg.content) {
            const rawContent = msg.content.trim();
            if (this.settings.exactCommandMatch) {
                isTestCommand = (rawContent === "!stankrecord-test");
                isRecordCommand = (rawContent === "!stankrecord" || rawContent === "!stankscore");
            } else {
                isTestCommand = (msg.content.includes("!stankrecord-test"));
                isRecordCommand = (msg.content.includes("!stankrecord") || msg.content.includes("!stankscore"));
            }
            if (isTestCommand) isRecordCommand = false;
        }

        if (!isRecordCommand && !isTestCommand) return;

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
                this.toast(`Routing auto-reply to #memes!`);
                shootReply = true;
            } else {
                this.toast(`Ignored command: #memes auto-reply disabled!`);
            }
        }

        if (shootReply) {
            if (isTestCommand) {
                this.sendBotReply(msg.channel_id, this.getRecordAnnouncementTemplate());
            } else {
                this.sendBotReply(msg.channel_id, this.getScoreTemplate());
            }
        }
    }

    getSettingsPanel() {
        const panel = document.createElement("div");
        panel.style.padding = "20px";
        panel.style.color = "var(--text-normal)";

        // --- EXACT MATCH SETTING ---
        const label0 = document.createElement("label");
        label0.style.display = "flex";
        label0.style.alignItems = "center";
        label0.style.gap = "10px";
        label0.style.fontSize = "16px";
        label0.style.cursor = "pointer";

        const checkbox0 = document.createElement("input");
        checkbox0.type = "checkbox";
        checkbox0.checked = this.settings.exactCommandMatch;
        checkbox0.style.width = "20px";
        checkbox0.style.height = "20px";
        checkbox0.style.cursor = "pointer";

        checkbox0.addEventListener("change", (e) => {
            this.settings.exactCommandMatch = e.target.checked;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Exact Command Match: ${e.target.checked ? "ON" : "OFF"}`);
        });

        label0.appendChild(checkbox0);
        label0.appendChild(document.createTextNode("Require exact text match for commands"));

        const note0 = document.createElement("div");
        note0.style.marginTop = "8px";
        note0.style.fontSize = "14px";
        note0.style.color = "var(--text-muted)";
        note0.innerText = "If checked, '!stankscore' must be the only text in the message to successfully trigger a reply. If unchecked, the bot will wildly reply even if the command keyword is embedded deep inside a longer paragraph.";

        panel.appendChild(label0);
        panel.appendChild(note0);

        // --- MEMES CHANNEL SETTING ---
        const label = document.createElement("label");
        label.style.display = "flex";
        label.style.alignItems = "center";
        label.style.gap = "10px";
        label.style.fontSize = "16px";
        label.style.cursor = "pointer";
        label.style.marginTop = "30px";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = this.settings.enableMemesReplies;
        checkbox.style.width = "20px";
        checkbox.style.height = "20px";
        checkbox.style.cursor = "pointer";

        checkbox.addEventListener("change", (e) => {
            this.settings.enableMemesReplies = e.target.checked;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Memes Channel Replies: ${e.target.checked ? "ON" : "OFF"}`);
        });

        label.appendChild(checkbox);
        label.appendChild(document.createTextNode("Enable commands auto-reply in #memes channel"));

        const note = document.createElement("div");
        note.style.marginTop = "8px";
        note.style.fontSize = "14px";
        note.style.color = "var(--text-muted)";
        note.innerText = "If checked, the bot will visibly reply to user's incoming !stankscore commands inside the #memes channel. If unchecked, it drops them and ONLY processes command tags silently in Direct Messages.";

        panel.appendChild(label);
        panel.appendChild(note);

        // --- RECORD BROKEN ANNOUNCEMENT SETTING ---
        const labelAnnounce = document.createElement("label");
        labelAnnounce.style.display = "flex";
        labelAnnounce.style.alignItems = "center";
        labelAnnounce.style.gap = "10px";
        labelAnnounce.style.fontSize = "16px";
        labelAnnounce.style.cursor = "pointer";
        labelAnnounce.style.marginTop = "30px";

        const checkboxAnnounce = document.createElement("input");
        checkboxAnnounce.type = "checkbox";
        checkboxAnnounce.checked = this.settings.enableRecordAnnouncement;
        checkboxAnnounce.style.width = "20px";
        checkboxAnnounce.style.height = "20px";
        checkboxAnnounce.style.cursor = "pointer";

        checkboxAnnounce.addEventListener("change", (e) => {
            this.settings.enableRecordAnnouncement = e.target.checked;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Record Announcement: ${e.target.checked ? "ON" : "OFF"}`);
        });

        labelAnnounce.appendChild(checkboxAnnounce);
        labelAnnounce.appendChild(document.createTextNode("Enable Record Broken specific announcements in #memes "));

        const noteAnnounce = document.createElement("div");
        noteAnnounce.style.marginTop = "8px";
        noteAnnounce.style.fontSize = "14px";
        noteAnnounce.style.color = "var(--text-muted)";
        noteAnnounce.innerText = "If checked, the bot will autonomously shoot out an announcement natively inside the #memes channel whenever the active chain physically breaks the highest recorded score.";

        panel.appendChild(labelAnnounce);
        panel.appendChild(noteAnnounce);

        // --- RECORD BROKEN TEMPLATE EDITOR ---
        const recordTemplateInput = document.createElement("input");
        recordTemplateInput.type = "text";
        recordTemplateInput.value = this.settings.recordTemplate || ":tada: New :Stank: record chain: {record}";
        recordTemplateInput.style.width = "100%";
        recordTemplateInput.style.marginTop = "10px";
        recordTemplateInput.style.padding = "8px";
        recordTemplateInput.style.fontFamily = "monospace";
        recordTemplateInput.style.backgroundColor = "var(--background-secondary)";
        recordTemplateInput.style.color = "var(--text-normal)";
        recordTemplateInput.style.border = "1px solid var(--text-normal)";
        recordTemplateInput.style.borderRadius = "4px";

        recordTemplateInput.addEventListener("change", (e) => {
            let val = e.target.value.trim();
            this.settings.recordTemplate = val;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Announcement Template Saved!`);
        });

        const noteRecordTemplate = document.createElement("div");
        noteRecordTemplate.style.marginTop = "5px";
        noteRecordTemplate.style.fontSize = "12px";
        noteRecordTemplate.style.color = "var(--text-muted)";
        noteRecordTemplate.innerText = "Custom Announcement Format. Available variables: {record}, :Stank:";

        panel.appendChild(recordTemplateInput);
        panel.appendChild(noteRecordTemplate);


        // --- NICKNAME SYNC SETTING ---
        const label2 = document.createElement("label");
        label2.style.display = "flex";
        label2.style.alignItems = "center";
        label2.style.gap = "10px";
        label2.style.fontSize = "16px";
        label2.style.cursor = "pointer";
        label2.style.marginTop = "30px";

        const checkbox2 = document.createElement("input");
        checkbox2.type = "checkbox";
        checkbox2.checked = this.settings.enableNicknameSync;
        checkbox2.style.width = "20px";
        checkbox2.style.height = "20px";
        checkbox2.style.cursor = "pointer";

        checkbox2.addEventListener("change", (e) => {
            this.settings.enableNicknameSync = e.target.checked;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Nickname Sync: ${e.target.checked ? "ON" : "OFF"}`);
            // Force the API to sync right now via a background command
            this.updateNickname();
        });

        label2.appendChild(checkbox2);
        label2.appendChild(document.createTextNode("Synchronize server nickname with ongoing chain"));

        const note2 = document.createElement("div");
        note2.style.marginTop = "8px";
        note2.style.fontSize = "14px";
        note2.style.color = "var(--text-muted)";
        note2.innerText = "If checked, automatically overwrites your Maphra server nickname on initial plugin load and upon every link added or shattered. Unchecking this immediately resets your nickname back to solely 'YourName' via API push.\n*Note: Discord limits all user nickname changes to approximately 10 per hour.*";

        panel.appendChild(label2);
        panel.appendChild(note2);

        // --- NICKNAME TEMPLATE EDITOR ---
        const nickTemplateInput = document.createElement("input");
        nickTemplateInput.type = "text";
        nickTemplateInput.value = this.settings.nicknameTemplate || "Randowned ({record}/{ongoing})";
        nickTemplateInput.style.width = "100%";
        nickTemplateInput.style.marginTop = "10px";
        nickTemplateInput.style.padding = "8px";
        nickTemplateInput.style.fontFamily = "monospace";
        nickTemplateInput.style.backgroundColor = "var(--background-secondary)";
        nickTemplateInput.style.color = "var(--text-normal)";
        nickTemplateInput.style.border = "1px solid var(--text-normal)";
        nickTemplateInput.style.borderRadius = "4px";

        nickTemplateInput.addEventListener("change", (e) => {
            let val = e.target.value.trim();
            this.settings.nicknameTemplate = val;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Nickname Template Saved!`);
            if (this.settings.enableNicknameSync) {
                this.updateNickname();
            }
        });

        const noteNickTemplate = document.createElement("div");
        noteNickTemplate.style.marginTop = "5px";
        noteNickTemplate.style.fontSize = "12px";
        noteNickTemplate.style.color = "var(--text-muted)";
        noteNickTemplate.innerText = "Custom Nickname Format. Available variables: {record}, {ongoing}";

        panel.appendChild(nickTemplateInput);
        panel.appendChild(noteNickTemplate);

        // --- SCORE TEMPLATE EDITOR SETTING ---
        const label3 = document.createElement("label");
        label3.style.display = "flex";
        label3.style.flexDirection = "column";
        label3.style.gap = "10px";
        label3.style.fontSize = "16px";
        label3.style.marginTop = "30px";

        label3.appendChild(document.createTextNode("Score Layout Template"));

        const textarea = document.createElement("textarea");
        textarea.value = this.settings.scoreTemplate || this.defaultTemplate;
        textarea.style.width = "100%";
        textarea.style.height = "80px";
        textarea.style.fontFamily = "monospace";
        textarea.style.padding = "10px";
        textarea.style.backgroundColor = "var(--background-secondary)";
        textarea.style.color = "var(--text-normal)";
        textarea.style.border = "1px solid var(--text-normal)";
        textarea.style.borderRadius = "4px";
        textarea.style.resize = "vertical";

        textarea.addEventListener("change", (e) => {
            let val = e.target.value.trim();
            if (val.indexOf("{record}") === -1 || val.indexOf("{ongoing}") === -1) {
                this.toast("Template must contain {record} and {ongoing}!", true);
                e.target.value = this.settings.scoreTemplate || this.defaultTemplate;
                return;
            }
            this.settings.scoreTemplate = val;
            BdApi.Data.save("StankScanner", "settings", this.settings);
            this.toast(`Score Template Saved!`);
            this.updateBio(); // Immediately push new format to server to prevent parse deadlock
        });

        const note3 = document.createElement("div");
        note3.style.marginTop = "8px";
        note3.style.fontSize = "14px";
        note3.style.color = "var(--text-muted)";
        note3.innerText = "Design the layout of your Bio and Stank Bot replies. Available placeholders: {record}, {ongoing}, and :Stank:\n\nThe plugin contains a dynamic RegExp parser under the hood, allowing it to mathematically read your Bio memory straight from whatever text shapes or symbols surround your variables!\nWARNING: If you edit this off of the layout that is physically sitting on your Server Bio and save it, the plugin will aggressively shoot an API push converting your real Server Bio to match this immediately to prevent memory deadlocks.";

        label3.appendChild(textarea);
        panel.appendChild(label3);
        panel.appendChild(note3);

        return panel;
    }
};
