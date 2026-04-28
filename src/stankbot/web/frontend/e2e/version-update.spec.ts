import { test, expect } from './fixtures';
import { Packr } from 'msgpackr';

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
		await expect(toast).toContainText('Updated version available');

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

		// Wait briefly and verify no update toast appears
		await page.waitForTimeout(1000);
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

		// Navigate to root to force clean WS reconnect with mismatched version
		await page.goto('/');

		// Wait for WS to connect AND boardState to be set (STATE message processed)
		await expect(page.locator('[data-testid="live-badge"]')).toHaveAttribute(
			'title',
			/Receiving live updates/,
			{ timeout: 15000 }
		);
		await expect(page.locator('[data-testid="tile-reactions"]')).toBeVisible({ timeout: 10000 });

		// Wait for toast to confirm mismatch was processed
		await expect(page.locator('[data-testid="update-toast"]')).toBeVisible({ timeout: 15000 });

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
		await page.waitForTimeout(3500);

		// Toast should still be visible
		await expect(toast).toBeVisible();
	});

	test('WS message type is 109 (VERSION_MISMATCH) on version mismatch', async ({ page }) => {
		// Get the server version
		const apiResp = await page.request.get('/api/version');
		const { version: serverVersion } = await apiResp.json();

		// Override server version via mock to guarantee mismatch
		await page.request.post('/api/mock/version', { data: { version: '99.0.0' } });

		// Intercept WebSocket frames at the Playwright layer
		const frameBuffers: Buffer[] = [];
		page.on('websocket', (ws) => {
			ws.on('framereceived', (frame) => {
				if (frame.payload instanceof Buffer) {
					frameBuffers.push(frame.payload);
				}
			});
		});

		// Set a mismatched version in localStorage
		await page.evaluate(
			(v) => localStorage.setItem('stankbot:version', v),
			`${serverVersion}.old`
		);

		// Reload to connect with mismatched version
		await page.reload();

		// Wait for the update toast to appear (confirms mismatch was processed)
		const toast = page.locator('[data-testid="update-toast"]');
		await expect(toast).toBeVisible({ timeout: 10000 });

		// Decode captured frames and find VERSION_MISMATCH (type 109)
		const packr = new Packr({ useRecords: false });
		const mismatchFrames = frameBuffers
			.map((buf) => {
				try { return packr.unpack(new Uint8Array(buf)); } catch { return null; }
			})
			.filter((msg): msg is { t: number; d: Record<string, unknown> } =>
				msg !== null && typeof msg.t === 'number' && msg.t === 109
			);
		expect(mismatchFrames.length).toBeGreaterThan(0);

		const mismatch = mismatchFrames[0].d as { server_version: string; client_version: string };
		expect(mismatch.server_version).toBe('99.0.0');
		expect(mismatch.client_version).toBe(`${serverVersion}.old`);
	});
});
