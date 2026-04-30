import type { Load } from '@sveltejs/kit';
import { loadWithFallback } from '$lib/api-utils';
import { apiFetch } from '$lib/api';
import type { MediaItem, MetricSnapshot } from '$lib/types';

export const load: Load = async ({ params, fetch }) => {
	const mediaId = Number(params.id);

	const item = await loadWithFallback<MediaItem | null>(
		() => apiFetch<MediaItem>(`/api/media/${mediaId}`, { fetch }),
		{ fallback: null }
	);

	let history: MetricSnapshot[] = [];
	if (item) {
		history = await loadWithFallback<MetricSnapshot[]>(
			() =>
				apiFetch<{ history: MetricSnapshot[] }>(
					`/api/media/${mediaId}/history?metric=view_count&days=30`,
					{ fetch }
				).then((r) => r.history),
			{ fallback: [] }
		);
	}

	return { item, history, mediaId };
};
