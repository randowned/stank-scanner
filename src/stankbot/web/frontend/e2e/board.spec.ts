import { test, expect } from './fixtures';

test.describe('Board', () => {
	test.beforeEach(async ({ mockLogin, newSession }) => {
		await mockLogin();
		await newSession();
	});

	test('board loads and shows guild name + live badge', async ({ page }) => {
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
		await expect(page.locator('[data-testid="live-badge"]')).toBeVisible();
		await expect(page.locator('[data-testid="connection-dot"]')).toBeVisible();
		await expect(page.locator('[data-testid="tile-reactions"]')).toBeVisible();
	});

	test('websocket connects and receives chain update on stank injection', async ({ page, injectStank }) => {
		const logs: string[] = [];
		page.on('console', (msg) => logs.push(`[${msg.type()}] ${msg.text()}`));
		page.on('pageerror', (err) => logs.push(`[pageerror] ${err.message}`));

		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/
		);

		console.log('Browser logs:', logs);

		await expect(page.locator('[data-testid="chain-counter"]')).toHaveText(/^0 /);

		await injectStank(123456789, 111, 'Alice');

		await expect(page.locator('[data-testid="chain-counter"]')).toHaveText(/^1 /);
	});

	test('websocket preserves exact Discord snowflake IDs', async ({ page }) => {
		const largeGuildId = '1482266782306799646';
		const largeUserId = '129508601730564096';

		const wsUrls: string[] = [];
		page.on('websocket', (ws) => wsUrls.push(ws.url()));

		await page.request.post('/auth/mock-login', {
			data: {
				user_id: largeUserId,
				username: 'SnowflakeTester',
				guilds: [{ id: largeGuildId, name: 'Big Server', permissions: 0x20 }],
				guild: largeGuildId,
				is_admin: true
			}
		});

		await page.goto('/');

		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/
		);

		const appWsUrl = wsUrls.find((u) => u.endsWith('/ws'));
		expect(appWsUrl).toBeDefined();
		expect(appWsUrl).not.toContain('guild_id=');
		expect(appWsUrl).not.toContain('user_id=');
	});

	test('chain break resets counter', async ({ page, injectStank, injectBreak }) => {
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/
		);

		await injectStank(123456789, 111, 'Alice');
		await injectStank(123456789, 222, 'Bob');

		await expect(page.locator('[data-testid="chain-counter"]')).toHaveText(/^2 /);

		await injectBreak(123456789, 333, 'Charlie');

		await expect(page.locator('[data-testid="chain-counter"]')).toHaveText(/^0 /);
	});

	test('leaderboard rows appear live via rank_update broadcast', async ({ page, injectStank }) => {
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/
		);

		const liveUserId = Date.now() % 1_000_000_000;
		const liveUser = `LiveUpdate_${liveUserId}`;

		await injectStank(123456789, liveUserId, liveUser);

		const row = page.locator(`[data-testid="rank-row"][href$="/player/${liveUserId}"]`);
		await expect(row).toBeVisible({ timeout: 5000 });
		const netText = await row.locator('[data-testid="net-score"]').textContent();
		expect(Number((netText ?? '0').trim())).toBeGreaterThan(0);
	});

	test('random events update the board', async ({ page, startRandomEvents, stopRandomEvents }) => {
		await startRandomEvents(1);

		await page.waitForTimeout(3500);

		await stopRandomEvents();

		const counterText = await page.locator('[data-testid="chain-counter"]').textContent();
		const rankingCount = await page.locator('[data-testid="rank-row"]').count();
		expect(counterText !== '0 / 0' || rankingCount > 0).toBeTruthy();
	});
});
