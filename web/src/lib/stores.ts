import { writable, derived, type Writable, type Readable } from 'svelte/store';
import type { User, BoardState, PlayerProfile, Badge, ChainSummary, SessionSummary } from '../app.d';

export const guildId: Writable<string | null> = writable(null);
export const user: Writable<User | null> = writable(null);
export const isAuthenticated: Readable<boolean> = derived(user, ($user) => $user !== null);

export const boardState: Writable<BoardState | null> = writable(null);
export const currentChain: Readable<number> = derived(boardState, ($state) => $state?.current ?? 0);
export const currentUnique: Readable<number> = derived(boardState, ($state) => $state?.current_unique ?? 0);

export const leaderboard: Readable<BoardState['rankings']> = derived(boardState, ($state) => $state?.rankings ?? []);

export const chainStarter: Readable<BoardState['chain_starter']> = derived(boardState, ($state) => $state?.chain_starter ?? null);
export const chainbreaker: Readable<BoardState['chainbreaker']> = derived(boardState, ($state) => $state?.chainbreaker ?? null);

export const playerProfiles: Writable<Map<number, PlayerProfile>> = writable(new Map());
export const selectedPlayerId: Writable<number | null> = writable(null);
export const selectedPlayer: Readable<PlayerProfile | null> = derived(
	[playerProfiles, selectedPlayerId],
	([$profiles, $id]) => ($id !== null ? $profiles.get($id) ?? null : null)
);

export const badges: Writable<Badge[]> = writable([]);

export const chains: Writable<ChainSummary[]> = writable([]);
export const sessions: Writable<SessionSummary[]> = writable([]);

export const connectionStatus: Writable<'connecting' | 'connected' | 'disconnected' | 'error'> = writable('disconnected');
export const wsLatency: Writable<number> = writable(0);

export const toasts: Writable<Toast[]> = writable([]);

export interface Toast {
	id: string;
	message: string;
	type: 'info' | 'success' | 'warning' | 'error';
	duration?: number;
}

export function addToast(message: string, type: Toast['type'] = 'info', duration = 3000) {
	const id = crypto.randomUUID();
	toasts.update((t) => [...t, { id, message, type, duration }]);
	if (duration > 0) {
		setTimeout(() => {
			toasts.update((t) => t.filter((x) => x.id !== id));
		}, duration);
	}
	return id;
}

export function removeToast(id: string) {
	toasts.update((t) => t.filter((x) => x.id !== id));
}