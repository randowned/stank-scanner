import { test, expect } from './fixtures';

test.describe('Version update notification', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin();
	});

	test('shows update toast when client version mismatches server version', async ({ page }) => {
		// Get the actual server version
		const apiResp = await page.request.get('/api/version');
		const { version: serverVersion } = await apiResp.json();
		expect(serverVersion).toBeTruthy();

		// Set a different version in localStorage
		await page.evaluate(
			(v) => localStorage.setItem('stankbot:version', v),
			`${serverVersion}.old`
		);

		// Reload to trigger fresh WS connect with version check
		await page.reload();

		// Wait for WS to connect
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/,
			{ timeout: 15000 }
		);

		// Wait for the update toast to appear
		const toast = page.locator('[data-testid="update-toast"]');
		await expect(toast).toBeVisible({ timeout: 10000 });
		await expect(toast).toContainText('new version is available');

		// Reload button should be visible
		const reloadBtn = page.locator('[data-testid="update-reload-btn"]');
		await expect(reloadBtn).toBeVisible();
		await expect(reloadBtn).toHaveText('Reload');
	});

	test('does not show update toast when versions match', async ({ page }) => {
		// Get the actual server version
		const apiResp = await page.request.get('/api/version');
		const { version: serverVersion } = await apiResp.json();

		// Set the same version in localStorage
		await page.evaluate(
			(v) => localStorage.setItem('stankbot:version', v),
			serverVersion
		);

		// Reload to trigger fresh WS connect
		await page.reload();

		// Wait for WS to connect
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/,
			{ timeout: 15000 }
		);

		// Wait a bit and verify no update toast appears
		await page.waitForTimeout(3000);
		const toast = page.locator('[data-testid="update-toast"]');
		await expect(toast).not.toBeVisible();
	});

	test('shows update toast on first visit (no stored version)', async ({ page }) => {
		// Ensure no version in localStorage
		await page.evaluate(() => localStorage.removeItem('stankbot:version'));

		// Reload to trigger fresh WS connect
		await page.reload();

		// Wait for WS to connect
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/,
			{ timeout: 15000 }
		);

		// Update toast should appear since client has no version stored
		const toast = page.locator('[data-testid="update-toast"]');
		await expect(toast).toBeVisible({ timeout: 10000 });
	});

	test('stores server version in localStorage after mismatch', async ({ page }) => {
		// Get the actual server version
		const apiResp = await page.request.get('/api/version');
		const { version: serverVersion } = await apiResp.json();

		// Set a different version
		await page.evaluate(
			(v) => localStorage.setItem('stankbot:version', v),
			`${serverVersion}.old`
		);

		// Reload
		await page.reload();

		// Wait for WS to connect
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/,
			{ timeout: 15000 }
		);

		// Wait for toast to confirm mismatch was processed
		await expect(page.locator('[data-testid="update-toast"]')).toBeVisible({ timeout: 10000 });

		// Verify localStorage was updated to the server version
		const storedVersion = await page.evaluate(() => localStorage.getItem('stankbot:version'));
		expect(storedVersion).toBe(serverVersion);
	});

	test('update toast persists and does not auto-dismiss', async ({ page }) => {
		// Set a different version in localStorage
		await page.evaluate(() => localStorage.setItem('stankbot:version', '0.0.0-old'));

		// Reload
		await page.reload();

		// Wait for WS to connect
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/,
			{ timeout: 15000 }
		);

		// Wait for toast
		const toast = page.locator('[data-testid="update-toast"]');
		await expect(toast).toBeVisible({ timeout: 10000 });

		// Wait longer than a normal toast would auto-dismiss (default is 3s)
		await page.waitForTimeout(5000);

		// Toast should still be visible
		await expect(toast).toBeVisible();
	});
});
