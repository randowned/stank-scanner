import { test, expect, adminUser } from './fixtures';

test.describe('Game events page', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin(adminUser);
	});

	test('events page shows stank and break entries after injection', async ({ page, injectStank, injectBreak }) => {
		const GUILD = 123456789;
		const STANKER = 7001;
		const BREAKER = 7002;

		await injectStank(GUILD, STANKER, 'StankerUser');
		await injectBreak(GUILD, BREAKER, 'BreakerUser');

		await page.goto('/admin/events');
		await expect(page.getByText('Game events')).toBeVisible({ timeout: 10000 });

		// Should see at least sp_base and chain_break type badges
		await expect(page.getByText('sp base').first()).toBeVisible({ timeout: 5000 });
		await expect(page.getByText('chain break').first()).toBeVisible({ timeout: 5000 });

		// Username should appear
		await expect(page.getByText('StankerUser').first()).toBeVisible();
	});

	test('events page shows reaction entries', async ({ page, injectStank, injectReaction }) => {
		const GUILD = 123456789;
		const STANKER = 8001;

		const result = await injectStank(GUILD, STANKER, 'StankerUser');

		// Inject reaction on the stank message
		await injectReaction(GUILD, result.message_id, 8002);

		await page.goto('/admin/events');
		await expect(page.getByText('sp reaction').first()).toBeVisible({ timeout: 10000 });
	});

	test('grep filter narrows results by event type', async ({ page, injectStank, injectBreak }) => {
		const GUILD = 123456789;
		const STANKER = 9001;
		const BREAKER = 9002;

		await injectStank(GUILD, STANKER, 'FilterUser');
		await injectBreak(GUILD, BREAKER, 'BreakerUser');

		await page.goto('/admin/events');

		// Wait for events to load
		await expect(page.getByText('sp base').first()).toBeVisible({ timeout: 10000 });

		// Type "break" in the filter
		const searchInput = page.locator('input[placeholder*="Search"]');
		await searchInput.fill('break');

		// Wait for debounce + re-fetch
		await page.waitForTimeout(500);

		// Should now show only break-related events
		await expect(page.getByText('chain break').first()).toBeVisible({ timeout: 5000 });
		// sp base should be gone (filtered out)
		await expect(page.getByText('sp base')).toHaveCount(0);
	});

	test('sidebar has Events link', async ({ page }) => {
		await page.goto('/admin');
		await expect(page.getByRole('link', { name: 'Events' }).first()).toBeVisible();
	});

	test('empty state shown when no events exist', async ({ page }) => {
		await page.goto('/admin/events');
		await expect(page.getByText('No events yet')).toBeVisible({ timeout: 10000 });
	});
});
