import { redirect } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';
import type { GuildInfo } from '$lib/types';

interface AuthResponse {
	user: { id: string; username: string; avatar: string | null } | null;
	guild_id: string | null;
	guild_name: string | null;
	is_admin: boolean;
	is_global_admin: boolean;
}

// Module-level cache — lives for the lifetime of the SPA tab.
// Only refetched on full page load (login, logout, guild switch).
let authCache: AuthResponse | null = null;
let guildsCache: GuildInfo[] | null = null;

export const load: LayoutLoad = async ({ fetch, url }) => {
	try {
		if (!authCache) {
			const authRes = await fetch('/auth');
			if (authRes.ok) {
				authCache = await authRes.json();
			} else {
				authCache = null;
				guildsCache = null;
			}
		}

		const auth = authCache;
		const user = auth?.user ?? null;
		const isPublicPath = url.pathname.includes('/auth') || url.pathname === '/';
		if (!user && !isPublicPath) {
			throw redirect(303, '/');
		}

		if (auth?.is_global_admin && guildsCache === null) {
			const guildsRes = await fetch('/api/guilds');
			if (guildsRes.ok) {
				guildsCache = await guildsRes.json();
			} else {
				guildsCache = [];
			}
		}

		return {
			user,
			guild_id: auth?.guild_id ?? null,
			guild_name: auth?.guild_name ?? null,
			is_admin: auth?.is_admin ?? false,
			is_global_admin: auth?.is_global_admin ?? false,
			guilds: guildsCache ?? []
		};
	} catch (e) {
		if (e && typeof e === 'object' && 'status' in e) throw e;

		return {
			user: null,
			guild_id: null,
			guild_name: null,
			is_admin: false,
			is_global_admin: false,
			guilds: [] as GuildInfo[]
		};
	}
};
