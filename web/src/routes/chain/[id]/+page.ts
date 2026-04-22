import type { PageLoad } from './$types';
import type { ChainSummary } from '../../../app.d';

export const load: PageLoad = async ({ params, fetch }) => {
	const chainId = params.id;

	try {
		const response = await fetch(`/v2/api/chain/${chainId}`);
		if (!response.ok) {
			return { chain: null };
		}
		const chain = (await response.json()) as ChainSummary;
		return { chain };
	} catch {
		return { chain: null };
	}
};