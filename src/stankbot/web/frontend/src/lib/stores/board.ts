import { writable, derived, type Writable, type Readable } from 'svelte/store';
import type { BoardState, ChainSummary, SessionSummary } from '$lib/types';

export const boardState: Writable<BoardState | null> = writable(null);

export const currentChain: Readable<number> = derived(
	boardState,
	($state) => $state?.current ?? 0
);

export const currentUnique: Readable<number> = derived(
	boardState,
	($state) => $state?.current_unique ?? 0
);

export const leaderboard: Readable<BoardState['rankings']> = derived(
	boardState,
	($state) => $state?.rankings ?? []
);

export const chainStarter: Readable<BoardState['chain_starter']> = derived(
	boardState,
	($state) => $state?.chain_starter ?? null
);

export const chainbreaker: Readable<BoardState['chainbreaker']> = derived(
	boardState,
	($state) => $state?.chainbreaker ?? null
);

export const chains: Writable<ChainSummary[]> = writable([]);
export const sessions: Writable<SessionSummary[]> = writable([]);
