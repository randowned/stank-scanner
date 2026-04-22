import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch, cookies, url }) => {
	const devMode = url.searchParams.get('dev') === 'true';

	if (devMode) {
		return {
			user: { id: '111', username: 'TestPlayer', avatar: null },
			guild_id: '123456789012345678',
			is_admin: true
		};
	}

	const response = await fetch('/v2/auth');
	const user = response.ok ? await response.json() : null;

	return {
		user,
		guild_id: cookies.get('active_guild_id')
	};
};