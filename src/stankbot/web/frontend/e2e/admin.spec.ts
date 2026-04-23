import { test, expect } from './fixtures';

test.describe('Admin dashboard', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin();
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

	// Non-admin redirect can't be tested under dev mock auth because
	// `_is_admin_from_session` returns True unconditionally in mock mode
	// (see stankbot.web.deps._is_admin_from_session). Covered in unit
	// tests for require_guild_admin instead.
});

test.describe('Admin templates preview', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin();
	});

	test('template page loads keys and renders preview', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByRole('heading', { name: 'Templates' })).toBeVisible();
		// Tabs are rendered from the template keys list.
		const tabs = page.getByRole('tablist');
		await expect(tabs).toBeVisible();
		// Preview pane uses our declared testid.
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });
	});
});
