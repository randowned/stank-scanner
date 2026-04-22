import type { PageLoad } from './$types';
import type { ChainSummary } from '../../app.d';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const response = await fetch('/v2/api/chains');
		if (!response.ok) {
			return { chains: [] };
		}
		const chains = (await response.json()) as ChainSummary[];
		return { chains };
	} catch {
		return { chains: [] };
	}
};