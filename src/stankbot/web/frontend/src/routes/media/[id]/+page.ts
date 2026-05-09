import type { Load } from '@sveltejs/kit';
import { loadWithFallback } from '$lib/api-utils';
import { apiFetch } from '$lib/api';
import type { MediaItem, ProviderDef } from '$lib/types';

export const load: Load = async ({ params, fetch }) => {
	const mediaId = Number(params.id);

	const item = await loadWithFallback<MediaItem | null>(
		() => apiFetch<MediaItem>(`/api/media/${mediaId}`, { fetch }),
		{ fallback: null }
	);

	const providers = await loadWithFallback<ProviderDef[]>(
		() => apiFetch<{ providers: ProviderDef[] }>('/api/media/providers', { fetch }).then((r) => r.providers),
		{ fallback: [] }
	);

	return { item, mediaId, providers };
};
