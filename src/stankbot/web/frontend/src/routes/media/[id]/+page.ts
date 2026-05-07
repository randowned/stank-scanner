import type { Load } from '@sveltejs/kit';
import { loadWithFallback } from '$lib/api-utils';
import { apiFetch } from '$lib/api';
import type { MediaItem, MetricSnapshot, ProviderDef, CompareData } from '$lib/types';

export interface ChartParams {
	metric: string;
	hours: number;
	resolution: string;
	mode: string;
	compareIds: string;
}

export const load: Load = async ({ params, fetch, url }) => {
	const mediaId = Number(params.id);

	const item = await loadWithFallback<MediaItem | null>(
		() => apiFetch<MediaItem>(`/api/media/${mediaId}`, { fetch }),
		{ fallback: null }
	);

	const providers = await loadWithFallback<ProviderDef[]>(
		() => apiFetch<{ providers: ProviderDef[] }>('/api/media/providers', { fetch }).then((r) => r.providers),
		{ fallback: [] }
	);

	const sp = url.searchParams;
	const metric = sp.get('metric') || (item?.media_type === 'spotify' ? 'playcount' : 'view_count');
	const hours = Number(sp.get('hours')) || 24;
	const resolution = sp.get('resolution') || 'auto';
	const mode = sp.get('mode') || 'delta';
	const compareIds = sp.get('compare') || '';

	let history: MetricSnapshot[] = [];
	let compare: CompareData | null = null;

	if (item) {
		let apiUrl: string;
		if (hours < 24) {
			apiUrl = `/api/media/${mediaId}/history?metric=${metric}&hours=${hours}`;
		} else {
			const days = Math.max(1, Math.round(hours / 24));
			apiUrl = `/api/media/${mediaId}/history?metric=${metric}&days=${days}`;
		}
		if (resolution !== 'auto' && /^(5min|15min|30min|hourly|daily|weekly|monthly)$/.test(resolution)) {
			apiUrl += `&aggregation=${resolution}&mode=${mode}`;
		}
		if (compareIds) {
			apiUrl += `&compare_ids=${compareIds}`;
		}

		const res = await loadWithFallback<{ history: MetricSnapshot[]; compare?: CompareData }>(
			() => apiFetch<{ history: MetricSnapshot[]; compare?: CompareData }>(apiUrl, { fetch }),
			{ fallback: { history: [] } }
		);
		history = res.history;
		compare = res.compare ?? null;
	}

	const chartParams: ChartParams = { metric, hours, resolution, mode, compareIds };

	return { item, history, compare, chartParams, mediaId, providers };
};
