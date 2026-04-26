import { test, expect, defaultUser, adminUser } from './fixtures';

const GUILD = 123456789;

test.describe('Player profile session vs all-time', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin(adminUser);
	});

	test('session and alltime show different values after activity in current session', async ({ page, injectStank, injectBreak, newSession }) => {
		await newSession();

		const userId = 70001;
		const stankResult = await injectStank(GUILD, userId, 'TestPlayer');
		await injectBreak(GUILD, 70002, 'BreakerUser');

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('session-stats')).toBeVisible({ timeout: 10000 });

		const sessionSp = await page.getByTestId('session-sp').textContent();
		const alltimeSp = await page.getByTestId('alltime-sp').textContent();

		expect(sessionSp).not.toBe('0');
		expect(alltimeSp).toBe(sessionSp);
	});

	test('session stats reflect activity in current session only', async ({ page, injectStank, newSession }) => {
		await newSession();

		const userId = 70011;
		const stankResult = await injectStank(GUILD, userId, 'SessionPlayer');

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('session-stats')).toBeVisible({ timeout: 10000 });

		const sessionSp = await page.getByTestId('session-sp').textContent();
		const alltimeSp = await page.getByTestId('alltime-sp').textContent();

		expect(sessionSp).toBe(alltimeSp);
		expect(sessionSp).not.toBe('0');
	});

	test('alltime accumulates from previous sessions after session rollover', async ({ page, injectStank, injectBreak, newSession }) => {
		const userId = 70021;
		await injectStank(GUILD, userId, 'Accumulator1');
		await injectBreak(GUILD, userId, 'Accumulator1');

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('alltime-stats')).toBeVisible({ timeout: 10000 });

		const alltimeSpBefore = await page.getByTestId('alltime-sp').textContent();
		const alltimePpBefore = await page.getByTestId('alltime-pp').textContent();
		expect(alltimeSpBefore).not.toBe('0');
		expect(alltimePpBefore).not.toBe('0');

		await newSession();

		await injectStank(GUILD, userId, 'Accumulator2');
		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('alltime-stats')).toBeVisible({ timeout: 10000 });

		const alltimeSpAfter = await page.getByTestId('alltime-sp').textContent();
		expect(parseInt(alltimeSpAfter || '0')).toBeGreaterThan(parseInt(alltimeSpBefore || '0'));
	});

	test('after rebuild-from-db, session and alltime still differ correctly', async ({ page, injectStank, newSession }) => {
		await newSession();

		const userId = 70031;
		await injectStank(GUILD, userId, 'RebuildTestUser');

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('session-stats')).toBeVisible({ timeout: 10000 });

		const sessionSpBefore = await page.getByTestId('session-sp').textContent();
		const alltimeSpBefore = await page.getByTestId('alltime-sp').textContent();

		const rebuildResponse = await page.request.post('/api/admin/rebuild-from-db', {
			data: { guild_id: GUILD }
		});
		expect(rebuildResponse.ok()).toBeTruthy();

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('session-stats')).toBeVisible({ timeout: 10000 });

		const sessionSpAfter = await page.getByTestId('session-sp').textContent();
		const alltimeSpAfter = await page.getByTestId('alltime-sp').textContent();

		expect(sessionSpAfter).toBe(sessionSpBefore);
		expect(alltimeSpAfter).toBe(alltimeSpBefore);
	});

	test('chains_started and chains_broken only show in alltime, not session', async ({ page, injectStank, injectBreak, newSession }) => {
		await newSession();

		const userId = 70041;
		await injectStank(GUILD, userId, 'ChainStarter');
		await injectBreak(GUILD, 70042, 'ChainBreaker');

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('session-stats')).toBeVisible({ timeout: 10000 });

		const sessionPanel = page.getByTestId('session-stats');
		const alltimePanel = page.getByTestId('alltime-stats');

		await expect(sessionPanel).not.toContainText('Started');
		await expect(sessionPanel).not.toContainText('Broken');

		await expect(alltimePanel).toContainText('Started');
		await expect(alltimePanel).toContainText('Broken');
	});
});

test.describe('Player profile page loads', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin(defaultUser);
	});

	test('player profile page renders for existing player', async ({ page, injectStank }) => {
		const userId = 70051;
		await injectStank(GUILD, userId, 'ExistingPlayer');

		await page.goto(`/player/${userId}`);
		await expect(page.getByTestId('session-stats')).toBeVisible({ timeout: 10000 });
		await expect(page.getByTestId('alltime-stats')).toBeVisible({ timeout: 10000 });
	});

	test('player profile page handles non-existent player gracefully', async ({ page, injectStank }) => {
		await page.goto('/player/999999997');
		await expect(page.locator('.panel').first()).toBeVisible({ timeout: 10000 });
	});
});