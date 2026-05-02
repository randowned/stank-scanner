import type { Load } from '@sveltejs/kit';
import { loadWithFallback } from '$lib/api-utils';
import { apiFetch } from '$lib/api';
import type { MediaItem, MetricSnapshot, ProviderDef } from '$lib/types';

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

	let history: MetricSnapshot[] = [];
	if (item) {
		const initialMetric = item.media_type === 'spotify' ? 'popularity' : 'view_count';
		history = await loadWithFallback<MetricSnapshot[]>(
			() =>
				apiFetch<{ history: MetricSnapshot[] }>(
					`/api/media/${mediaId}/history?metric=${initialMetric}&hours=24`,
					{ fetch }
				).then((r) => r.history),
			{ fallback: [] }
		);
	}

	return { item, history, mediaId, providers };
};
