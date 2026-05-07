import { test, expect, adminUser, guildAdminUser } from './fixtures';

test.describe('Auth guard — unauthenticated redirects', () => {
	test('/auth returns 200 null when unauthenticated', async ({ page }) => {
		const res = await page.request.get('/auth');
		expect(res.status()).toBe(200);
		expect(await res.json()).toBeNull();
	});

	test('/auth/login redirects to mock-login', async ({ page }) => {
		const res = await page.request.get('/auth/login', { maxRedirects: 0 });
		expect(res.status()).toBe(302);
		expect(res.headers()['location']).toContain('/auth/mock-login');
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

test.describe('Auth guard — non-admin user', () => {
	test('non-admin can access board', async ({ mockLogin, page }) => {
		await mockLogin();
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
	});

	test('non-admin can access sessions', async ({ mockLogin, page }) => {
		await mockLogin();
		await page.goto('/sessions');
		await expect(page.getByText('Session History')).toBeVisible();
	});

	test('non-admin is redirected from admin page', async ({ mockLogin, page }) => {
		await mockLogin();
		await page.goto('/admin');
		await expect(page).toHaveURL(/\/$/);
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
	});

	test('non-admin /api/guilds returns 403', async ({ mockLogin, page }) => {
		await mockLogin();
		const res = await page.request.get('/api/guilds');
		expect(res.status()).toBe(403);
	});

	test('non-admin /api/admin/settings returns 403', async ({ mockLogin, page }) => {
		await mockLogin();
		const res = await page.request.get('/api/admin/settings');
		expect(res.status()).toBe(403);
	});
});

test.describe('Auth guard — admin user', () => {
	test('admin can access board', async ({ mockLogin, page }) => {
		await mockLogin(adminUser);
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
	});

	test('admin can access sessions', async ({ mockLogin, page }) => {
		await mockLogin(adminUser);
		await page.goto('/sessions');
		await expect(page.getByText('Session History')).toBeVisible();
	});

	test('admin can access admin page', async ({ mockLogin, page }) => {
		await mockLogin(adminUser);
		await page.goto('/admin');
		await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
	});

	test('admin /api/guilds returns 200', async ({ mockLogin, mockBotGuilds, page }) => {
		await mockLogin(adminUser);
		await mockBotGuilds([{ id: 123456789, name: 'Alpha Server' }]);
		const res = await page.request.get('/api/guilds');
		expect(res.status()).toBe(200);
		const guilds = await res.json();
		expect(guilds.length).toBeGreaterThanOrEqual(1);
	});

	test('admin /api/admin/settings returns 200', async ({ mockLogin, page }) => {
		await mockLogin(adminUser);
		const res = await page.request.get('/api/admin/settings');
		expect(res.status()).toBe(200);
	});
});

test.describe('Auth guard — guild-only admin user', () => {
	test('guild admin can access admin page', async ({ mockLogin, page }) => {
		await mockLogin(guildAdminUser);
		await page.goto('/admin');
		await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
	});

	test('guild admin /api/admin/settings returns 200', async ({ mockLogin, page }) => {
		await mockLogin(guildAdminUser);
		const res = await page.request.get('/api/admin/settings');
		expect(res.status()).toBe(200);
	});

	test('guild admin /api/guilds returns 403 (not global admin)', async ({ mockLogin, page }) => {
		await mockLogin(guildAdminUser);
		const res = await page.request.get('/api/guilds');
		expect(res.status()).toBe(403);
	});

	test('guild admin can access board', async ({ mockLogin, page }) => {
		await mockLogin(guildAdminUser);
		await expect(page.locator('[data-testid="guild-name"]')).toBeVisible();
	});
});
