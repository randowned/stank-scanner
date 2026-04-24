import { test, expect } from './fixtures';

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
