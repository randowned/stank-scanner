import type { PageLoad } from './$types';
import type { SessionSummary } from '$lib/types';
import { apiFetch } from '$lib/api';
import { loadWithFallback } from '$lib/api-utils';

export const load: PageLoad = async ({ fetch }) => {
	const sessions = await loadWithFallback<SessionSummary[]>(
		() => apiFetch<SessionSummary[]>('/api/sessions', { fetch }),
		{ fallback: [] }
	);
	return { sessions };
};
