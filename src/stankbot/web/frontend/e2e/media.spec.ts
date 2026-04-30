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
		await injectMedia({ guildId: GUILD, slug: 'my-test-video' });
		await page.goto('/media');
		await expect(page.getByTestId('page-header')).toBeVisible();
		await expect(page.getByTestId('media-card')).toBeVisible({ timeout: 10000 });
	});

	test('navigates to media detail page', async ({ page, injectMedia }) => {
		const { id } = await injectMedia({ guildId: GUILD, slug: 'my-detail-video' });
		await page.goto('/media');
		await page.getByTestId('media-card').first().click();
		await expect(page).toHaveURL(new RegExp(`/media/${id}`));
		await expect(page.getByTestId('page-header')).toBeVisible({ timeout: 10000 });
	});
});
