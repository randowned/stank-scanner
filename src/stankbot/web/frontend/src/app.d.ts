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
			is_admin?: boolean;
			env?: string;
			guilds?: GuildInfo[];
		}
	}
}

export {};
