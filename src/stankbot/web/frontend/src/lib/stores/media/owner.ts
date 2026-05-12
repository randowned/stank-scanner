import { writable } from 'svelte/store';

export interface OwnerMetricUpdate {
	ownerId: number;
	metrics: Array<{ key: string; value: number; fetchedAt: string }>;
}

/** Latest owner metric update pushed via WebSocket.
 * Consumers (detail page) subscribe and patch the owner card tiles. */
export const ownerMetricUpdates = writable<OwnerMetricUpdate | null>(null);
