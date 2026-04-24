import { test, expect } from './fixtures';

test.describe('Auth guard — unauthenticated redirects', () => {
	test('/auth returns 401 when unauthenticated', async ({ page }) => {
		const res = await page.request.get('/auth');
		expect(res.status()).toBe(401);
	});

	test('/auth/login redirects to mock-login with next param for root', async ({ page }) => {
		const res = await page.request.get('/auth/login?next=%2F', { maxRedirects: 0 });
		expect(res.status()).toBe(302);
		expect(res.headers()['location']).toContain('/auth/mock-login');
		expect(res.headers()['location']).toContain('next=');
	});

	test('/auth/login redirects with next param for deep link', async ({ page }) => {
		const res = await page.request.get('/auth/login?next=%2Fplayer%2F999', { maxRedirects: 0 });
		expect(res.status()).toBe(302);
		expect(res.headers()['location']).toContain('/auth/mock-login?next=/player/999');
	});

	test('/auth/mock-login redirects back to next destination', async ({ page }) => {
		const res = await page.request.get('/auth/mock-login?next=/player/999', { maxRedirects: 0 });
		expect(res.status()).toBe(303);
		expect(res.headers()['location']).toBe('/player/999');
	});

	test('full redirect chain lands unauthenticated user at login then back', async ({ page }) => {
		await page.goto('/');
		await page.context().clearCookies();
		await page.goto('/');
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible({ timeout: 15000 });
	});
});

test.describe('Auth guard — login page accessible', () => {
	test('/auth/login does not cause redirect loop', async ({ page }) => {
		const res = await page.request.get('/auth/login', { maxRedirects: 0 });
		expect(res.status()).toBeLessThan(500);
	});
});

test.describe('Auth guard — authenticated access', () => {
	test('authenticated user can access board', async ({ mockLogin, page }) => {
		await mockLogin();
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
	});

	test('authenticated user can access sessions', async ({ mockLogin, page }) => {
		await mockLogin();
		await page.goto('/sessions');
		await expect(page.getByText('Session History')).toBeVisible();
	});

	test('authenticated user can access admin', async ({ mockLogin, page }) => {
		await mockLogin();
		await page.goto('/admin');
		await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
	});
});

test.describe('Auth guard — API protection', () => {
	test('unauthenticated /api/guilds returns 401', async ({ page }) => {
		const res = await page.request.get('/api/guilds');
		expect(res.status()).toBe(401);
	});

	test('unauthenticated /api/admin/settings returns 401', async ({ page }) => {
		const res = await page.request.get('/api/admin/settings');
		expect(res.status()).toBe(401);
	});
});
