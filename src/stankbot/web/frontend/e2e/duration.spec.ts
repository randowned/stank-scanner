import { test, expect } from './fixtures';

test.describe('Duration', () => {
	test.beforeEach(async ({ mockLogin, newSession }) => {
		await mockLogin();
		await newSession();
	});

	test('dashboard shows countdown in 2-unit format', async ({ page }) => {
		const countdown = page.locator('[data-testid="session-countdown"]');
		await expect(countdown).toBeVisible();

		const text = await countdown.textContent();
		expect(text).toBeTruthy();
		expect(text!.trim()).toMatch(/^\d+[hmd]/);
	});

	test('dashboard countdown shows tooltip on hover', async ({ page }) => {
		const trigger = page.locator('[data-testid="session-countdown"] [data-testid="tooltip-root"]');
		await expect(trigger).toBeVisible();

		await trigger.hover();

		const tooltip = page.locator('[data-testid="tooltip-popover"]');
		await expect(tooltip).toBeVisible({ timeout: 2000 });
	});

	test('dashboard countdown shows tooltip on focus', async ({ page }) => {
		const trigger = page.locator('[data-testid="session-countdown"] [data-testid="tooltip-root"]');
		await expect(trigger).toBeVisible();

		await trigger.focus();

		const tooltip = page.locator('[data-testid="tooltip-popover"]');
		await expect(tooltip).toBeVisible({ timeout: 2000 });
	});

	test('chain detail page shows duration and tooltip', async ({ page, injectStank, injectBreak }) => {
		const GUILD = 123456789;

		await injectStank(GUILD, 10001, 'ChainUser');
		await injectStank(GUILD, 10002, 'ChainUser2');
		await injectStank(GUILD, 10003, 'ChainUser3');
		await injectBreak(GUILD, 10099, 'ChainBreaker');

		await page.goto('/sessions');
		await page.locator('a[href*="/session/"]').first().click();
		const chainLink = page.locator('a[href*="/chain/"]').first();
		await chainLink.click();

		const durationEl = page.locator('.grid-cols-2 .text-xl').last();
		await expect(durationEl).toBeVisible();
		await expect(durationEl).not.toHaveText('');

		await durationEl.locator('[data-testid="tooltip-root"]').hover();

		const tooltip = page.locator('[data-testid="tooltip-popover"]');
		await expect(tooltip).toBeVisible({ timeout: 2000 });
		await expect(tooltip).toContainText('Start');
		await expect(tooltip).toContainText('End');
	});

	test('chain detail has no Started/Ended footer', async ({ page, injectStank, injectBreak }) => {
		const GUILD = 123456789;

		await injectStank(GUILD, 20001, 'FooterUser');
		await injectBreak(GUILD, 20099, 'FooterBreaker');

		await page.goto('/sessions');
		await page.locator('a[href*="/session/"]').first().click();
		await page.locator('a[href*="/chain/"]').first().click();

		const startedEndedText = page.locator('text=Started:');
		await expect(startedEndedText).toHaveCount(0);
	});
});
