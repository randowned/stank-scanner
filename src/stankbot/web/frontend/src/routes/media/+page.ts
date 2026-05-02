import type { Load } from '@sveltejs/kit';
import { loadWithFallback } from '$lib/api-utils';
import { apiFetch } from '$lib/api';
import type { MediaItem, ProviderDef } from '$lib/types';

export const load: Load = async ({ fetch, parent }) => {
	const { user } = await parent();
	if (!user) return { items: [], guild_name: '', providers: [] };

	const items = await loadWithFallback<MediaItem[]>(
		() => apiFetch<{ items: MediaItem[] }>('/api/media', { fetch }).then((r) => r.items),
		{ fallback: [] }
	);

	const providers = await loadWithFallback<ProviderDef[]>(
		() => apiFetch<{ providers: ProviderDef[] }>('/api/media/providers', { fetch }).then((r) => r.providers),
		{ fallback: [] }
	);

	return { items, providers };
};
