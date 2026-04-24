import { redirect } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';
import type { GuildInfo } from '$lib/types';

export const load: LayoutLoad = async ({ fetch, url }) => {
	try {
		const [authRes, envRes] = await Promise.all([
			fetch('/auth'),
			fetch('/api/env')
		]);

		const user = authRes.ok ? await authRes.json() : null;

		const isPublicPath = url.pathname.includes('/auth') || url.pathname === '/';
		if (!user && !isPublicPath) {
			throw redirect(303, '/');
		}

		const envData = envRes.ok
			? await envRes.json()
			: { env: 'production', guild_id: null, is_admin: false };

		let guilds: GuildInfo[] = [];
		if (user) {
			const guildsRes = await fetch('/api/guilds');
			if (guildsRes.ok) {
				guilds = await guildsRes.json();
			}
		}

		return {
			user,
			guild_id: envData.guild_id,
			is_admin: envData.is_admin,
			env: envData.env,
			invite_url: envData.invite_url as string | null,
			guilds
		};
	} catch (e) {
		if (e && typeof e === 'object' && 'status' in e) throw e;

		const isPublicPath = url.pathname.includes('/auth') || url.pathname === '/';
		if (!isPublicPath) {
			throw redirect(303, '/');
		}

		return {
			user: null,
			guild_id: null,
			is_admin: false,
			env: 'production',
			invite_url: null,
			guilds: [] as GuildInfo[]
		};
	}
};
