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

	test('popover opens and closes on click', async ({ page }) => {
		const badge = page.locator('[data-testid="online-badge"]');
		await expect(badge).toBeVisible();
		await badge.click();
		await page.waitForTimeout(300);
		const popover = page.locator('[data-testid="online-popover"]');
		await expect(popover).toBeVisible({ timeout: 5000 });
		await expect(popover).toContainText('Online Users');
		await page.locator('body').click({ position: { x: 10, y: 10 } });
		await expect(popover).not.toBeVisible();
	});

	test('popover lists logged-in admin user', async ({ page }) => {
		const badge = page.locator('[data-testid="online-badge"]');
		await expect(badge).toBeVisible();
		await badge.click();
		await page.waitForTimeout(300);
		const popover = page.locator('[data-testid="online-popover"]');
		await expect(popover).toBeVisible({ timeout: 5000 });
		const rows = page.locator('[data-testid="online-user-row"]');
		await expect(rows.first()).toBeVisible({ timeout: 5000 });
		await expect(rows.first()).toContainText(adminUser.username);
	});
});

test.describe('Online users — not admin', () => {
	test('non-admin user sees LiveBadge instead of OnlineBadge', async ({ page, mockLogin }) => {
		await mockLogin();
		await expect(page.locator('[data-testid="online-badge"]')).not.toBeVisible();
		await expect(page.locator('[data-testid="live-badge"]')).toBeVisible();
	});
});
