import { writable, type Writable } from 'svelte/store';
import type { Badge } from '$lib/types';

/**
 * Side-channel for WebSocket-originated events that need UI surfacing
 * beyond simple state updates (toasts, confetti, flash highlights).
 *
 * `ws.ts` publishes here and stays free of UI concerns; subscribers in
 * the layout / pages decide how to present each event kind.
 */

export type WsEvent =
	| { kind: 'connected' }
	| { kind: 'disconnected'; code: number; reason: string }
	| { kind: 'reconnect-failed' }
	| { kind: 'error'; code: string; message: string }
	| { kind: 'achievement'; userId: string; badge: Badge }
	| { kind: 'session'; action: 'start' | 'end'; sessionId: number }
	| { kind: 'update-available'; serverVersion: string; clientVersion: string }
	| { kind: 'media-milestone'; mediaItemId: number; title: string;
	    metricKey: string; milestoneValue: number; newValue: number;
	    thumbnailUrl?: string | null; name?: string | null }
	| { kind: 'owner-milestone'; ownerId: number; ownerName: string;
	    mediaType: string; metricKey: string; milestoneValue: number;
	    newValue: number; thumbnailUrl?: string | null; externalUrl?: string | null };

/** Latest event; subscribers react on change. `null` between events. */
export const lastWsEvent: Writable<WsEvent | null> = writable(null);

export function emitWsEvent(event: WsEvent): void {
	lastWsEvent.set(event);
}
