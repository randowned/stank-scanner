import type { PageLoad } from './$types';
import type { ChainSummary } from '$lib/types';
import { apiFetch } from '$lib/api';
import { loadWithFallback } from '$lib/api-utils';

interface ChainResponse extends ChainSummary {
	names?: Record<string, string>;
}

export const load: PageLoad = async ({ params, fetch }) => {
	const chainId = params.id;
	const chain = await loadWithFallback<ChainResponse | null>(
		() => apiFetch<ChainResponse>(`/api/chain/${chainId}`, { fetch }),
		{ fallback: null }
	);

	return { chain, names: chain?.names ?? {} };
};
