import { writable, derived, type Writable, type Readable } from 'svelte/store';
import type { User, GuildInfo } from '$lib/types';

export const guildId: Writable<string | null> = writable(null);

export const user: Writable<User | null> = writable(null);

export const isAuthenticated: Readable<boolean> = derived(user, ($user) => $user !== null);

export const guilds: Writable<GuildInfo[]> = writable([]);

export const activeGuild: Readable<GuildInfo | null> = derived(
	[guilds, guildId],
	([$guilds, $guildId]) => $guilds.find((g) => g.id === $guildId) ?? null
);
