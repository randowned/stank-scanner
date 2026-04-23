import { writable } from 'svelte/store';

export const user = writable<null | Record<string, unknown>>(null);
export const guildId = writable<string | null>(null);
export const connectionStatus = writable<string>('disconnected');
export const wsLatency = writable<number>(0);
export const boardState = writable<null | Record<string, unknown>>(null);

interface Toast {
	id: number;
	message: string;
	type: string;
	duration: number;
}

export const toasts = writable<Toast[]>([]);

export function addToast(message: string, type = 'info', duration = 3000) {
	toasts.update(t => [...t, { id: Date.now(), message, type, duration }]);
}

export function removeToast(id: number) {
	toasts.update(t => t.filter(x => x.id !== id));
}
