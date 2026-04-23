import { writable, type Writable } from 'svelte/store';
import type { Toast, ToastKind } from '$lib/types';

export const toasts: Writable<Toast[]> = writable([]);

export function addToast(message: string, type: ToastKind = 'info', duration = 3000): string {
	const id = crypto.randomUUID();
	toasts.update((t) => [...t, { id, message, type, duration }]);
	if (duration > 0) {
		setTimeout(() => {
			toasts.update((t) => t.filter((x) => x.id !== id));
		}, duration);
	}
	return id;
}

export function removeToast(id: string): void {
	toasts.update((t) => t.filter((x) => x.id !== id));
}

export type { Toast, ToastKind };
