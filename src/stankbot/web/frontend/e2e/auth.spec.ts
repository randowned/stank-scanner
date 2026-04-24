import { test, expect } from './fixtures';

async function getHasSession(page: import('@playwright/test').Page): Promise<string | undefined> {
	// Read via JS — page.context().cookies() may miss cookies set via document.cookie
	const cookieStr: string = await page.evaluate(() => document.cookie);
	const match = cookieStr.split(';').map((c) => c.trim()).find((c) => c.startsWith('has_session='));
	return match?.split('=')[1];
}

test.describe('Auth', () => {
	test('shows welcome page for unauthenticated visitors', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByText('MAPHRA Discord community')).toBeVisible();
		await expect(page.getByText('Continue with Discord')).toBeVisible();
	});

	test('auto-redirects to mock login in dev mode', async ({ page }) => {
		await page.goto('/auth/login');
		// Should land on board (auto-logged in via mock auth redirect)
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
	});

	test('mock login with custom user', async ({ mockLogin, page }) => {
		await mockLogin({ user_id: 999, username: 'CustomBot', guilds: [{ id: 123456789, name: 'TestGuild', permissions: 0 }] });
		// Verify the user is recognized by checking the /auth API
		const authRes = await page.request.get('/auth');
		expect(authRes.ok()).toBeTruthy();
		const user = await authRes.json();
		expect(user.username).toBe('CustomBot');
	});
});

test.describe('has_session presence cookie', () => {
	test('is set after login', async ({ mockLogin, page }) => {
		await mockLogin();
		// Wait for board to confirm full hydration (syncSessionCookie runs during layout load)
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
		expect(await getHasSession(page)).toBe('1');
	});

	test('is cleared after logout', async ({ mockLogin, page }) => {
		await mockLogin();
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
		await page.goto('/auth/logout');
		await expect(page.getByText('MAPHRA Discord community')).toBeVisible();
		expect(await getHasSession(page)).toBeUndefined();
	});

	test('missing has_session with valid session does not cause login loop', async ({ mockLogin, page }) => {
		await mockLogin();
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();

		// Simulate pre-v2.17.3: session cookie exists but presence cookie is absent
		await page.evaluate(() => { document.cookie = 'has_session=; path=/; max-age=0'; });
		expect(await getHasSession(page)).toBeUndefined();

		// Navigate — layout calls /auth, finds user, backfills has_session
		await page.goto('/');
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
		expect(await getHasSession(page)).toBe('1');
	});

	test('is absent and stays absent for unauthenticated visitors', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByText('MAPHRA Discord community')).toBeVisible();
		expect(await getHasSession(page)).toBeUndefined();
	});
});
