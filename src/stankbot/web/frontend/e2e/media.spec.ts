import { test, expect } from './fixtures';

const GUILD = 123456789;

test.describe('Media admin page', () => {
	test.beforeEach(async ({ mockLogin, clearMedia, page }) => {
		await mockLogin({ user_id: 222222222, username: 'E2E Admin', is_global_admin: true, is_guild_admin: true });
		await clearMedia();
	});

	test('admin can navigate to add', async ({ page }) => {
		await page.goto('/admin/media');
		await page.getByTestId('media-add-btn').click();
		await expect(page).toHaveURL(/\/admin\/media\/add/);
	});

	test('admin list shows injected media', async ({ page, injectMedia }) => {
		await injectMedia({ guildId: GUILD, slug: 'admin-test' });
		await page.goto('/admin/media');
		await expect(page.getByTestId('media-admin-row')).toBeVisible({ timeout: 10000 });
	});

	test('admin sees empty state', async ({ page }) => {
		await page.goto('/admin/media');
		await expect(page.getByTestId('page-header')).toBeVisible({ timeout: 10000 });
		await expect(page.getByText('No media')).toBeVisible();
	});

	test('redirects non-admin', async ({ page, mockLogin }) => {
		await mockLogin();
		await page.goto('/admin/media');
		await expect(page).not.toHaveURL(/\/admin\/media/);
	});
});

test.describe('Media page', () => {
	test.beforeEach(async ({ mockLogin, clearMedia }) => {
		await mockLogin();
		await clearMedia();
	});

	test('shows empty state when no media exist', async ({ page }) => {
		await page.goto('/media');
		await expect(page.getByTestId('page-header')).toBeVisible({ timeout: 10000 });
		await expect(page.getByText('No media yet')).toBeVisible();
	});

	test('shows media cards after injection', async ({ page, injectMedia }) => {
		await injectMedia({ guildId: GUILD, slug: 'my-test-video', historyDays: 7 });
		await page.goto('/media');
		await expect(page.getByTestId('page-header')).toBeVisible();
		await expect(page.getByTestId('media-card')).toBeVisible({ timeout: 10000 });
	});

	test('media card shows all three metric values', async ({ page, injectMedia }) => {
		await injectMedia({ guildId: GUILD, slug: 'multi-metric-test', historyDays: 7 });
		await page.goto('/media');
		await expect(page.getByTestId('media-card')).toBeVisible({ timeout: 10000 });
		const metricsEl = page.getByTestId('media-metrics').first();
		await expect(metricsEl).toBeVisible();
		// Should contain all three metric icons
		const text = await metricsEl.textContent();
		expect(text).toContain('👁️');
		expect(text).toContain('👍');
		expect(text).toContain('💬');
	});

	test('navigates to media detail page', async ({ page, injectMedia }) => {
		const { id } = await injectMedia({ guildId: GUILD, slug: 'my-detail-video', historyDays: 7 });
		await page.goto('/media');
		await page.getByTestId('media-card').first().click();
		await expect(page).toHaveURL(new RegExp(`/media/${id}`));
		await expect(page.getByTestId('page-header')).toBeVisible({ timeout: 10000 });
	});

	test('compare mode navigates to detail page with query params', async ({ page, injectMedia }) => {
		const item1 = await injectMedia({ guildId: GUILD, slug: 'compare-video-1', historyDays: 7 });
		const item2 = await injectMedia({ guildId: GUILD, slug: 'compare-video-2', historyDays: 7 });
		await page.goto('/media');
		await expect(page.getByTestId('media-compare-toggle')).toBeVisible({ timeout: 10000 });

		// Enter compare mode
		await page.getByTestId('media-compare-toggle').click();

		// Select both cards
		const checks = page.getByTestId('media-select-check');
		await checks.first().click();
		await checks.last().click();

		// Click compare
		await page.getByTestId('media-compare-go').click();

		// Should navigate to first item's detail page with compare query param containing the second ID
		await expect(page).toHaveURL(new RegExp(`/media/${item1.id}\\?compare=${item2.id}`));
		await expect(page.getByTestId('page-header')).toBeVisible({ timeout: 10000 });
	});
});
