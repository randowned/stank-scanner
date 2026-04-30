import { test, expect, adminUser } from './fixtures';

test.describe('Datetime serialization', () => {
	test.beforeEach(async ({ mockLogin, newSession }) => {
		await mockLogin(adminUser);
		await newSession();
	});

	test('chain API response includes +00:00 in all datetime fields', async ({ page, injectStank }) => {
		const GUILD = 123456789;
		const STANKER = 6001;

		const stank = await injectStank(GUILD, STANKER, 'TimeTestUser');
		const chainId = stank.chain_id;

		const res = await page.request.get(`/api/chain/${chainId}`);
		expect(res.ok()).toBeTruthy();

		const body = await res.json();

		// Top-level fields
		expect(body.started_at).toMatch(/\+00:00$/);

		// Timeline items
		expect(Array.isArray(body.timeline)).toBeTruthy();
		for (const item of body.timeline) {
			if (item.created_at) {
				expect(item.created_at).toMatch(/\+00:00$/);
			}
		}
	});

	test('session list API returns +00:00 in datetime fields', async ({ page, injectStank }) => {
		const GUILD = 123456789;
		const STANKER = 6002;

		await injectStank(GUILD, STANKER, 'SessionTimeTest');

		const res = await page.request.get('/api/sessions');
		expect(res.ok()).toBeTruthy();

		const sessions = await res.json();
		expect(Array.isArray(sessions)).toBeTruthy();
		expect(sessions.length).toBeGreaterThan(0);

		for (const s of sessions) {
			if (s.started_at) {
				expect(s.started_at).toMatch(/\+00:00$/);
			}
		}
	});

	test('player API returns +00:00 in last_stank_at', async ({ page, injectStank }) => {
		const GUILD = 123456789;
		const STANKER = 6003;

		await injectStank(GUILD, STANKER, 'PlayerTimeTest');

		const res = await page.request.get(`/api/player/${STANKER}`);
		expect(res.ok()).toBeTruthy();

		const body = await res.json();
		if (body.last_stank_at) {
			expect(body.last_stank_at).toMatch(/\+00:00$/);
		}
	});
});
