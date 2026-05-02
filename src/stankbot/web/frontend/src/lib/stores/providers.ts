import { writable, get } from 'svelte/store';
import { apiFetch } from '$lib/api';
import type { ProviderDef } from '$lib/types';

export const providersByType = writable<Record<string, ProviderDef>>({});

let loadPromise: Promise<Record<string, ProviderDef>> | null = null;

export async function loadProviders(): Promise<Record<string, ProviderDef>> {
	const current = get(providersByType);
	if (Object.keys(current).length > 0) return current;
	if (loadPromise) return loadPromise;
	loadPromise = (async () => {
		try {
			const res = await apiFetch<{ providers: ProviderDef[] }>('/api/media/providers');
			const map: Record<string, ProviderDef> = {};
			for (const p of res.providers) map[p.type] = p;
			providersByType.set(map);
			return map;
		} catch {
			return {};
		} finally {
			loadPromise = null;
		}
	})();
	return loadPromise;
}
