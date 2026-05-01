import { test as base, expect as baseExpect, type Page } from '@playwright/test';

export const expect = baseExpect;

async function waitForBackend(page: Page, timeoutMs = 10000): Promise<void> {
	const started = Date.now();
	while (Date.now() - started < timeoutMs) {
		try {
			const resp = await page.request.get('/ping');
			if (resp.ok()) return;
		} catch {
			// backend not reachable yet
		}
		await new Promise((r) => setTimeout(r, 250));
	}
	throw new Error(
		`Backend not reachable at /ping after ${timeoutMs}ms. ` +
			'Is the backend running? Run `npm run e2e` to auto-start it.'
	);
}

export interface MockUser {
	user_id: number;
	username: string;
	avatar?: string | null;
	guild?: number;
	is_global_admin?: boolean;
	is_guild_admin?: boolean;
}

export const defaultUser: MockUser = {
	user_id: 111111111,
	username: 'E2E Tester',
	avatar: null,
	guild: 123456789,
	is_global_admin: false,
	is_guild_admin: false
};

export const adminUser: MockUser = {
	user_id: 222222222,
	username: 'E2E Admin',
	avatar: null,
	guild: 123456789,
	is_global_admin: true,
	is_guild_admin: true
};

export interface BotGuild {
	id: number;
	name: string;
	icon?: string | null;
}

export const test = base.extend<{
	mockLogin: (user?: MockUser) => Promise<void>;
	mockBotGuilds: (guilds: BotGuild[]) => Promise<void>;
	newSession: () => Promise<void>;
	injectStank: (guildId: number, userId: number, displayName: string) => Promise<void>;
	injectBreak: (guildId: number, userId: number, displayName: string) => Promise<void>;
	injectReaction: (guildId: number, messageId: number, userId: number) => Promise<void>;
	startRandomEvents: (interval?: number) => Promise<void>;
	stopRandomEvents: () => Promise<void>;
	injectMedia: (opts?: { guildId?: number; mediaType?: string; slug?: string; historyDays?: number }) => Promise<{ id: number; slug: string }>;
	clearMedia: (guildId?: number) => Promise<void>;
}>({
	mockLogin: async ({ page }, use) => {
		await use(async (user = defaultUser) => {
			await waitForBackend(page);
			const response = await page.request.post('/auth/mock-login', { data: user });
			expect(response.ok()).toBeTruthy();
			// Clear frontend caches so fresh data is fetched after login
			await page.evaluate(() => {
				try {
					sessionStorage.removeItem('stankbot:auth');
					sessionStorage.removeItem('stankbot:guilds');
				} catch {}
			});
			await page.goto('/');
		});
	},

	mockBotGuilds: async ({ page }, use) => {
		await use(async (guilds) => {
			const response = await page.request.post('/api/mock/bot-guilds', { data: { guilds } });
			expect(response.ok()).toBeTruthy();
			// Clear frontend guilds cache so next page load fetches fresh data
			await page.evaluate(() => {
				try { sessionStorage.removeItem('stankbot:guilds'); } catch {}
			});
		});
	},

	newSession: async ({ page }, use) => {
		await use(async () => {
			// Break any active chain so the counter resets to 0, then start a new session
			await page.request.post('/api/mock/break', { data: {} });
			await page.request.post('/api/mock/session/end', { data: {} });
			await page.reload();
		});
	},

	injectStank: async ({ page }, use) => {
		await use(async (guildId, userId, displayName) => {
			const response = await page.request.post('/api/mock/stank', {
				data: { guild_id: guildId, user_id: userId, display_name: displayName }
			});
			if (!response.ok()) {
				const body = await response.text().catch(() => 'unknown');
				console.error('injectStank failed:', response.status(), body);
			}
			expect(response.ok()).toBeTruthy();
			return response.json() as Promise<{ message_id: number; chain_id: number; chain_length: number; sp_awarded: number }>;
		});
	},

	injectBreak: async ({ page }, use) => {
		await use(async (guildId, userId, displayName) => {
			const response = await page.request.post('/api/mock/break', {
				data: { guild_id: guildId, user_id: userId, display_name: displayName }
			});
			if (!response.ok()) {
				const body = await response.text().catch(() => 'unknown');
				console.error('injectBreak failed:', response.status(), body);
			}
			expect(response.ok()).toBeTruthy();
		});
	},

	injectReaction: async ({ page }, use) => {
		await use(async (guildId, messageId, userId) => {
			const response = await page.request.post('/api/mock/reaction', {
				data: { guild_id: guildId, message_id: messageId, user_id: userId }
			});
			if (!response.ok()) {
				const body = await response.text().catch(() => 'unknown');
				console.error('injectReaction failed:', response.status(), body);
			}
			expect(response.ok()).toBeTruthy();
		});
	},

	startRandomEvents: async ({ page }, use) => {
		await use(async (interval = 2) => {
			await page.request.post('/api/mock/random/start', { data: { interval } });
		});
	},

	stopRandomEvents: async ({ page }, use) => {
		await use(async () => {
			await page.request.post('/api/mock/random/stop');
		});
	},

	injectMedia: async ({ page }, use) => {
		await use(async (opts = {}) => {
			const guildId = opts.guildId ?? 123456789;
			const mediaType = opts.mediaType ?? 'youtube';
			const slug = opts.slug ?? `e2e-test-${Date.now() % 100000}`;
			const historyDays = opts.historyDays ?? 30;
			const response = await page.request.post('/api/mock/media', {
				data: { guild_id: guildId, media_type: mediaType, slug, history_days: historyDays }
			});
			if (!response.ok()) {
				const body = await response.text().catch(() => 'unknown');
				console.error('injectMedia failed:', response.status(), body);
			}
			expect(response.ok()).toBeTruthy();
			return response.json() as Promise<{ id: number; slug: string }>;
		});
	},

	clearMedia: async ({ page }, use) => {
		await use(async (guildId = 123456789) => {
			await page.request.post('/api/mock/clear-media', { data: { guild_id: guildId } });
		});
	}
});
