import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url }) => {
	const devMode = url.searchParams.get('dev') === 'true';

	if (devMode) {
		return {
			user: { id: '111', username: 'TestPlayer', avatar: null },
			guild_id: '123456789012345678',
			is_admin: true
		};
	}

	try {
		const response = await fetch('/v2/auth');
		const user = response.ok ? await response.json() : null;

		return {
			user,
			guild_id: null
		};
	} catch {
		return {
			user: null,
			guild_id: null
		};
	}
};