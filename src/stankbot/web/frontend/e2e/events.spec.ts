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
		await expect(page.getByTestId('events-table')).toBeVisible({ timeout: 10000 });

		await expect(page.getByText('sp base').first()).toBeVisible({ timeout: 5000 });
		await expect(page.getByText('chain break').first()).toBeVisible({ timeout: 5000 });
		await expect(page.getByText('StankerUser').first()).toBeVisible();
	});

	test('events page shows reaction entries', async ({ page, injectStank, injectReaction }) => {
		const GUILD = 123456789;
		const STANKER = 8001;

		const result = await injectStank(GUILD, STANKER, 'StankerUser');
		await injectReaction(GUILD, result.message_id, 8002);

		await page.goto('/admin/events');
		await expect(page.getByTestId('events-table')).toBeVisible({ timeout: 10000 });
		await expect(page.getByText('sp reaction').first()).toBeVisible({ timeout: 10000 });
	});

	test('grep filter narrows results by event type', async ({ page, injectStank, injectBreak }) => {
		const GUILD = 123456789;
		const STANKER = 9001;
		const BREAKER = 9002;

		await injectStank(GUILD, STANKER, 'FilterUser');
		await injectBreak(GUILD, BREAKER, 'BreakerUser');

		await page.goto('/admin/events');
		await expect(page.getByTestId('events-table')).toBeVisible({ timeout: 10000 });
		await expect(page.getByText('sp base').first()).toBeVisible({ timeout: 5000 });

		const searchInput = page.locator('input[placeholder*="Search"]');
		await searchInput.fill('break');

		// Wait for search filter to apply (debounced)
		await page.waitForFunction(() => {
			const rows = document.querySelectorAll('[data-testid="events-table"] tbody tr');
			for (const row of rows) {
				if (row.textContent?.includes('chain break')) return true;
			}
			return false;
		}, { timeout: 3000 });

		await expect(page.getByText('chain break').first()).toBeVisible({ timeout: 5000 });
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

	test('new event appears via WebSocket after injection', async ({ page, injectStank }) => {
		const GUILD = 123456789;

		await page.goto('/admin/events');
		await expect(page.getByTestId('events-table')).toBeVisible({ timeout: 10000 });

		// Inject a stank — WS should push the event and the table should update
		await injectStank(GUILD, 10001, 'WSTester');

		// The new event should appear at the top without page reload
		await expect(page.getByText('sp base').first()).toBeVisible({ timeout: 5000 });
		const rows = page.locator('[data-testid="events-table"] tbody tr');
		await expect(rows.first()).toBeVisible();
	});

	test('WS-injected event row shows a date in the When column', async ({ page, injectStank }) => {
		const GUILD = 123456789;

		await page.goto('/admin/events');
		await expect(page.getByTestId('events-table')).toBeVisible({ timeout: 10000 });

		await injectStank(GUILD, 50001, 'DateCheckUser');

		// Find the row for our user and check its When cell is not empty
		const targetRow = page
			.locator('[data-testid="events-table"] tbody tr')
			.filter({ hasText: 'DateCheckUser' })
			.first();
		await expect(targetRow).toBeVisible({ timeout: 5000 });

		const whenCell = targetRow.locator('td').first();
		const cellText = await whenCell.innerText();
		expect(cellText.trim().length).toBeGreaterThan(0);
	});

	test('dashboard has Events tile', async ({ page }) => {
		await page.goto('/admin');
		await expect(page.getByText('Game event log')).toBeVisible();
	});
});
