import { writable, type Writable } from 'svelte/store';

export interface ChainBreakInfo {
	user_id: number;
	display_name: string;
	avatar_url: string | null;
	pp_loss: number;
}

export const activeChainBreak: Writable<ChainBreakInfo | null> = writable(null);
