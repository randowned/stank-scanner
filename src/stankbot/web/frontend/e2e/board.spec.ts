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
		// format is now "+N SP" or "-N SP"
		expect(netText).toMatch(/^\+/);
	});

	test('reaction increments reactions tile and row counter', async ({
		page,
		injectStank,
		injectReaction
	}) => {
		const GUILD = 123456789;
		const STANKER = 7001;
		const REACTOR = 7002;

		// Plant a stank so there's a message to react to
		const stank = await injectStank(GUILD, STANKER, 'StankUser');
		const messageId = stank.message_id;

		// Wait for the stank broadcast to fully settle by checking the chain counter
		await expect(page.locator('[data-testid="chain-counter"]')).toHaveText(/^1 /, { timeout: 5000 });

		// Inject a reaction from a different user
		await injectReaction(GUILD, messageId, REACTOR);

		// Wait for the reactor's row to appear — this confirms the reaction's
		// rank_update broadcast was processed, so no stale stank broadcast can
		// overwrite the tile after we assert on it.
		const reactorRow = page.locator(`[data-testid="rank-row"][href$="/player/${REACTOR}"]`);
		await expect(reactorRow).toBeVisible({ timeout: 5000 });
		const subtitle = reactorRow.locator('.text-xs.text-muted');
		await expect(subtitle).toContainText('reacts', { timeout: 5000 });

		// Chain reactions tile (first number) should now be 1
		const reactionsTile = page.locator('[data-testid="tile-reactions"]').locator('div').first();
		await expect(reactionsTile).toHaveText(/^1 \/ /, { timeout: 5000 });
	});

	test('pagination loads rows with stanks/reactions counters', async ({
		page,
		injectStank,
		injectReaction
	}) => {
		const GUILD = 123456789;

		// Create more than PAGE_SIZE (20) users to trigger pagination
		for (let i = 0; i < 25; i++) {
			await injectStank(GUILD, 8000 + i, `PaginatedUser${i}`);
		}

		// Wait for the last few rows to appear so pagination is active
		await expect(page.locator('[data-testid="rank-row"]')).toHaveCount(20, { timeout: 10000 });

		// Scroll down and wait for more rows to load
		await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
		await page.waitForTimeout(2000);

		// Verify some rows show counters (stanks/reacted format)
		const rowsWithCounters = page.locator('[data-testid="rank-row"]').filter({ hasText: /Stanks/ });
		const count = await rowsWithCounters.count();
		expect(count).toBeGreaterThan(0);
	});

	test('subtitle shows session totals on board', async ({
		page,
		injectStank,
		injectReaction
	}) => {
		const GUILD = 123456789;
		const STANKER = 9001;
		const REACTOR = 9002;

		// Plant a stank
		const stank = await injectStank(GUILD, STANKER, 'CounterUser');
		const messageId = stank.message_id;

		// Wait for chain to be active
		await expect(page.locator('[data-testid="chain-counter"]')).toHaveText(/^1 /, { timeout: 5000 });

		// Add reaction
		await injectReaction(GUILD, messageId, REACTOR);

		// Find the reactor's row and verify counters format
		const reactorRow = page.locator(`[data-testid="rank-row"][href$="/player/${REACTOR}"]`);
		await expect(reactorRow).toBeVisible({ timeout: 5000 });
		const subtitle = reactorRow.locator('.text-xs.text-muted');

		// Should show "X Stanks · Y reacts" format
		await expect(subtitle).toHaveText(/\d+ Stanks · \d+ reacts/);
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
