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
	| { kind: 'achievement'; userId: number; badge: Badge }
	| { kind: 'session'; action: 'start' | 'end'; sessionId: number };

/** Latest event; subscribers react on change. `null` between events. */
export const lastWsEvent: Writable<WsEvent | null> = writable(null);

export function emitWsEvent(event: WsEvent): void {
	lastWsEvent.set(event);
}
