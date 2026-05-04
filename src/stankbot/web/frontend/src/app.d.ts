/// <reference types="@sveltejs/kit" />

import type { User, GuildInfo } from '$lib/types';

declare global {
	namespace App {
		interface Locals {
			user: User | null;
		}
		interface PageData {
			user: User | null;
			guild_id?: string | null;
			guild_name?: string | null;
			is_admin?: boolean;
			is_global_admin?: boolean;
			is_bot_owner?: boolean;
			guilds?: GuildInfo[];
		}
	}
}

export {};
