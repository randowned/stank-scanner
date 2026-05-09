import { writable } from 'svelte/store';

export interface MediaMetricUpdate {
	mediaItemId: number;
	metricKey: string;
	value: number;
	fetchedAt: string;
}

/** Queue of recent metric updates pushed via WebSocket. Consumers subscribe
 * and apply visual indicators (StatTile flash, card highlight) then
 * dequeue after a timeout. */
export const mediaMetricUpdates = writable<MediaMetricUpdate[]>([]);
