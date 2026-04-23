import { writable, derived, type Writable, type Readable } from 'svelte/store';
import type { Badge, PlayerProfile } from '$lib/types';

export const playerProfiles: Writable<Map<number, PlayerProfile>> = writable(new Map());

export const selectedPlayerId: Writable<number | null> = writable(null);

export const selectedPlayer: Readable<PlayerProfile | null> = derived(
	[playerProfiles, selectedPlayerId],
	([$profiles, $id]) => ($id !== null ? $profiles.get($id) ?? null : null)
);

export const badges: Writable<Badge[]> = writable([]);
