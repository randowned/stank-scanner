import type { PageLoad } from './$types';
import type { ChainSummary } from '$lib/types';
import { apiFetch } from '$lib/api';
import { loadWithFallback } from '$lib/api-utils';

interface PlayerName {
	user_id: string;
	display_name: string;
}

export const load: PageLoad = async ({ params, fetch }) => {
	const chainId = params.id;
	const chain = await loadWithFallback<ChainSummary | null>(
		() => apiFetch<ChainSummary>(`/api/chain/${chainId}`, { fetch }),
		{ fallback: null }
	);

	let names: Record<string, string> = {};
	if (chain && chain.contributors.length > 0) {
		const ids = Array.from(
			new Set(chain.contributors.map(([uid]) => String(uid)))
		);
		names = await loadWithFallback<Record<string, string>>(
			async () => {
				const res = await apiFetch<PlayerName[]>(
					`/api/players/batch?ids=${ids.join(',')}`,
					{ fetch }
				);
				return Object.fromEntries(res.map((r) => [r.user_id, r.display_name]));
			},
			{ fallback: {} }
		);
	}

	return { chain, names };
};
