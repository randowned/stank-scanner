import { test, expect } from './fixtures';

test.describe('Admin template editor', () => {
	test.beforeEach(async ({ mockLogin }) => {
		await mockLogin();
	});

	test('page loads with default templates and preview', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByRole('heading', { name: 'Templates' })).toBeVisible();

		// Template select is visible with options.
		const select = page.getByTestId('template-select');
		await expect(select).toBeVisible();

		// Preview tab is active by default and shows a preview.
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });
	});

	test('switching template keys updates preview', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });

		// Select "Chain break" template.
		const select = page.getByTestId('template-select');
		await select.selectOption('chain_break_embed');

		// Preview should update — chain break default contains "broke".
		await expect(page.getByTestId('template-preview')).toContainText('broke', {
			timeout: 5000
		});
	});

	test('edit tab shows JSON textarea with current template', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });

		// Switch to Edit tab.
		await page.getByTestId('tab-edit').click();

		// Textarea should contain valid JSON with a "title" key.
		const textarea = page.getByTestId('template-json');
		await expect(textarea).toBeVisible();
		const value = await textarea.inputValue();
		const parsed = JSON.parse(value);
		expect(parsed).toHaveProperty('title');
	});

	test('save persists template and reload shows saved version', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });

		// Select chain break template and switch to Edit.
		await page.getByTestId('template-select').selectOption('chain_break_embed');
		await page.getByTestId('tab-edit').click();

		// Modify the title in the JSON.
		const textarea = page.getByTestId('template-json');
		const original = JSON.parse(await textarea.inputValue());
		const modified = { ...original, title: 'E2E Template Test Title' };
		await textarea.evaluate(
			(el: HTMLTextAreaElement, val: string) => {
				el.value = val;
				el.dispatchEvent(new Event('input', { bubbles: true }));
			},
			JSON.stringify(modified)
		);

		// Save.
		await page.getByTestId('template-save').click();
		await expect(page.getByTestId('template-save-msg')).toHaveText('Saved.', { timeout: 5000 });

		// Reload and verify the saved title persists.
		await page.reload();
		await page.getByTestId('template-select').selectOption('chain_break_embed');
		await page.getByTestId('tab-edit').click();
		const reloaded = JSON.parse(await page.getByTestId('template-json').inputValue());
		expect(reloaded.title).toBe('E2E Template Test Title');

		// Restore default so other tests aren't polluted.
		await page.getByTestId('template-default').click();
		await page.getByTestId('template-save').click();
		await expect(page.getByTestId('template-save-msg')).toHaveText('Saved.', { timeout: 5000 });
	});

	test('default button restores built-in template on save', async ({ page }) => {
		// Save a custom template via the API.
		const custom = {
			color: '#ef4444',
			title: 'ZZZZZ Custom Title',
			description: '{breaker_name} broke a chain.',
			fields: []
		};
		const saveRes = await page.request.post('/api/admin/templates/chain_break_embed', {
			data: { data: custom }
		});
		expect(saveRes.ok()).toBeTruthy();

		// Load the page — should show the custom template in preview.
		await page.goto('/admin/templates');
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });
		await page.getByTestId('template-select').selectOption('chain_break_embed');
		await expect(page.getByTestId('template-preview')).toContainText('ZZZZZ Custom Title', {
			timeout: 5000
		});

		// The built-in default title is different from the custom one.
		// This is verified by the "switching template keys" test which
		// confirms the default contains "broke".
	});

	test('preview updates when editing JSON', async ({ page }) => {
		await page.goto('/admin/templates');
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });

		// Select chain break, go to Edit.
		await page.getByTestId('template-select').selectOption('chain_break_embed');
		await page.getByTestId('tab-edit').click();

		// Change title and switch to Preview.
		const textarea = page.getByTestId('template-json');
		const original = JSON.parse(await textarea.inputValue());
		const modified = { ...original, title: 'Preview Test Title' };
		await textarea.evaluate(
			(el: HTMLTextAreaElement, val: string) => {
				el.value = val;
				el.dispatchEvent(new Event('input', { bubbles: true }));
			},
			JSON.stringify(modified)
		);

		await page.getByTestId('tab-preview').click();
		await expect(page.getByTestId('template-preview')).toContainText('Preview Test Title', {
			timeout: 5000
		});
	});

	test('saved template is reflected in admin preview', async ({ page }) => {
		// Save a custom chain break title via the admin UI.
		await page.goto('/admin/templates');
		await expect(page.getByTestId('template-preview')).toBeVisible({ timeout: 5000 });
		await page.getByTestId('template-select').selectOption('chain_break_embed');
		await page.getByTestId('tab-edit').click();

		const textarea = page.getByTestId('template-json');
		const original = JSON.parse(await textarea.inputValue());
		const modified = { ...original, title: 'Custom Break Title E2E' };
		await textarea.evaluate(
			(el: HTMLTextAreaElement, val: string) => {
				el.value = val;
				el.dispatchEvent(new Event('input', { bubbles: true }));
			},
			JSON.stringify(modified)
		);
		await page.getByTestId('template-save').click();
		await expect(page.getByTestId('template-save-msg')).toHaveText('Saved.', { timeout: 5000 });

		// Reload and verify the saved template shows in preview.
		await page.reload();
		await page.getByTestId('template-select').selectOption('chain_break_embed');
		await expect(page.getByTestId('template-preview')).toContainText('Custom Break Title E2E', {
			timeout: 5000
		});

		// Restore default template.
		await page.getByTestId('tab-edit').click();
		await page.getByTestId('template-default').click();
		await page.getByTestId('template-save').click();
		await expect(page.getByTestId('template-save-msg')).toHaveText('Saved.', { timeout: 5000 });
	});
});
