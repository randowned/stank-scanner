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

	test('unauthenticated / shows welcome page instead of redirecting', async ({ page }) => {
		const res = await page.goto('/');
		expect(res?.status()).toBeLessThan(500);
		await expect(page.getByText('MAPHRA Discord community')).toBeVisible();
	});

	test('deep link /sessions redirects unauthenticated user to /', async ({ page }) => {
		await page.goto('/sessions');
		await expect(page).toHaveURL(/\/$/);
		await expect(page.getByText('MAPHRA Discord community')).toBeVisible();
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

	test('unauthenticated /api/env returns 200 (intentionally public)', async ({ page }) => {
		const res = await page.request.get('/api/env');
		expect(res.status()).toBe(200);
	});

	// Note: data endpoints (/api/board, /api/sessions, /api/player/*, etc.) use
	// require_guild_member which auto-fabricates a user in dev-mock mode.
	// Their 401 behavior in production is covered by the dependency's unit logic.
});
