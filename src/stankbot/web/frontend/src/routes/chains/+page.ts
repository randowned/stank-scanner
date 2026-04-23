import type { PageLoad } from './$types';
import type { ChainSummary } from '$lib/types';
import { apiFetch } from '$lib/api';
import { loadWithFallback } from '$lib/api-utils';

export const load: PageLoad = async ({ fetch }) => {
	const chains = await loadWithFallback<ChainSummary[]>(
		() => apiFetch<ChainSummary[]>('/api/chains', { fetch }),
		{ fallback: [] }
	);
	return { chains };
};
