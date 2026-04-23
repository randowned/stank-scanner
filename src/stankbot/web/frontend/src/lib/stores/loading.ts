import { writable, derived } from 'svelte/store';

export const pendingRequests = writable(0);
export const isLoading = derived(pendingRequests, (n) => n > 0);

export function beginRequest(): void {
	pendingRequests.update((n) => n + 1);
}

export function endRequest(): void {
	pendingRequests.update((n) => Math.max(0, n - 1));
}
