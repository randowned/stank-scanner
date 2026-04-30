import { test, expect, adminUser } from './fixtures';

test.describe('Online users badge (admin)', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin(adminUser);
	});

	test('shows online badge with count in header', async ({ page }) => {
		const badge = page.locator('[data-testid="online-badge"]');
		await expect(badge).toBeVisible();
		await expect(badge.locator('[data-testid="online-badge-count"]')).toContainText(/online/);
	});

	test('badge shows green dot when connected', async ({ page }) => {
		const dot = page.locator('[data-testid="online-badge-dot"]');
		await expect(dot).toBeVisible();
	});
});

test.describe('Online users — not admin', () => {
	test('non-admin user sees LiveBadge instead of OnlineBadge', async ({ page, mockLogin }) => {
		await mockLogin();
		await expect(page.locator('[data-testid="online-badge"]')).not.toBeVisible();
		await expect(page.locator('[data-testid="live-badge"]')).toBeVisible();
	});
});
