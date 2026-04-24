import { test, expect } from './fixtures';

test.describe('Player profile page', () => {
	test.beforeEach(async ({ mockLogin, newSession }) => {
		await mockLogin();
		await newSession();
	});

	test('player profile loads after stank injection', async ({ page, injectStank }) => {
		const GUILD = 123456789;
		const USER = 7001;

		await injectStank(GUILD, USER, 'TestPlayer');
		await page.goto(`/player/${USER}`);

		await expect(page.getByText('TestPlayer')).toBeVisible({ timeout: 10000 });
		await expect(page.getByRole('heading', { name: 'Session' })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'All-time' })).toBeVisible();
	});

	test('player profile shows SP and PP values', async ({ page, injectStank, injectBreak }) => {
		const GUILD = 123456789;
		const STANKER = 7002;
		const BREAKER = 7003;

		await injectStank(GUILD, STANKER, 'StankerUser');
		await injectBreak(GUILD, BREAKER, 'BreakerUser');

		await page.goto(`/player/${STANKER}`);
		await expect(page.getByText('StankerUser')).toBeVisible({ timeout: 10000 });
		await expect(page.getByText('SP').first()).toBeVisible();
	});
});

test.describe('Session detail page', () => {
	test.beforeEach(async ({ mockLogin, newSession }) => {
		await mockLogin();
		await newSession();
	});

	test('session detail page loads with session data', async ({ page, injectStank }) => {
		const GUILD = 123456789;

		await injectStank(GUILD, 9001, 'SessionUser');

		await page.goto('/sessions');
		await expect(page.getByText('Session History')).toBeVisible({ timeout: 10000 });

		// Click first session card (a.panel element)
		const sessionLink = page.locator('a[href*="/session/"]').first();
		await sessionLink.click();

		// Session detail should show the Summary card heading
		await expect(page.getByRole('heading', { name: 'Summary' })).toBeVisible({ timeout: 10000 });
	});
});

test.describe('Sessions list page', () => {
	test.beforeEach(async ({ mockLogin, newSession }) => {
		await mockLogin();
		await newSession();
	});

	test('sessions list shows entries after activity', async ({ page, injectStank }) => {
		const GUILD = 123456789;

		await injectStank(GUILD, 10001, 'ListUser');
		await page.goto('/sessions');

		await expect(page.getByText('Session History')).toBeVisible({ timeout: 10000 });
		const sessionLinks = page.locator('a[href*="/session/"]');
		await expect(sessionLinks.first()).toBeVisible({ timeout: 10000 });
	});
});
