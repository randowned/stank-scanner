import { test, expect, adminUser } from './fixtures';

test.describe('Admin dashboard', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin(adminUser);
	});

	test('admin page renders tiles when user is admin', async ({ page }) => {
		await page.goto('/admin');
		await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible();
		await expect(page.getByText('Settings', { exact: true }).first()).toBeVisible();
		await expect(page.getByText('Templates', { exact: true }).first()).toBeVisible();
		await expect(page.getByText('Audit log').first()).toBeVisible();
	});

	test('sidebar links navigate between admin pages', async ({ page }) => {
		await page.goto('/admin');
		await page.getByRole('link', { name: /Settings/ }).first().click();
		await expect(page).toHaveURL(/\/admin\/settings$/);
		await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
	});
});

test.describe('Admin templates preview', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin(adminUser);
	});

	test('template page loads keys and renders preview', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByRole('heading', { name: 'Templates' })).toBeVisible();
		await expect(page.getByTestId('template-select')).toBeVisible();
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });
	});
});

test.describe('Admin admins page', () => {
	test.beforeEach(async ({ mockLogin, page }) => {
		await mockLogin(adminUser);
		// Clean up any stale admin roles/users from previous runs
		const doc = await page.request.get('/api/admin/roles').then((r) => r.json()).catch(() => ({ role_ids: [], global_user_ids: [] }));
		for (const uid of doc.global_user_ids || []) {
			await page.request.post('/api/admin/roles/users/remove', { data: { user_id: Number(uid) } }).catch(() => {});
		}
		for (const rid of doc.role_ids || []) {
			await page.request.post('/api/admin/roles/remove', { data: { role_id: Number(rid) } }).catch(() => {});
		}
	});

	test('renders page with heading and content', async ({ page }) => {
		await page.goto('/admin/admins');
		await expect(page.getByRole('heading', { name: 'Admins' })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Guild admin roles' })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Global admin users' })).toBeVisible();
	});

	test('add user button is visible', async ({ page }) => {
		await page.goto('/admin/admins');
		await expect(page.getByTestId('add-user-btn')).toBeVisible({ timeout: 5000 });
	});

	test('add role button is visible', async ({ page }) => {
		await page.goto('/admin/admins');
		await expect(page.getByTestId('add-role-btn')).toBeVisible({ timeout: 5000 });
	});

	test('API: add and remove global admin user', async ({ page }) => {
		let res = await page.request.post('/api/admin/roles/users/add', { data: { user_id: 888888888 } });
		expect(res.status()).toBe(200);

		res = await page.request.post('/api/admin/roles/users/remove', { data: { user_id: 888888888 } });
		expect(res.status()).toBe(200);
	});

	test('API: add and remove guild admin role', async ({ page }) => {
		let res = await page.request.post('/api/admin/roles/add', { data: { role_id: 999999999 } });
		expect(res.status()).toBe(200);

		res = await page.request.post('/api/admin/roles/remove', { data: { role_id: 999999999 } });
		expect(res.status()).toBe(200);
	});
});
