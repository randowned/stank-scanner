import type { PageLoad } from './$types';
import { apiFetch } from '$lib/api';
import { loadWithFallback } from '$lib/api-utils';

interface SessionChain {
	chain_id: number;
	started_at: string | null;
	broken_at: string | null;
	length: number;
	unique_contributors: number;
	starter_user_id: number | null;
	broken_by_user_id: number | null;
}

interface SessionDetail {
	session_id: number;
	started_at: string | null;
	ended_at: string | null;
	chains_started: number;
	chains_broken: number;
	top_earner: [number, number] | null;
	top_breaker: [number, number] | null;
	chains?: SessionChain[];
}

export const load: PageLoad = async ({ params, fetch }) => {
	const sessionId = Number(params.id);
	const session = await loadWithFallback<SessionDetail | null>(
		() => apiFetch<SessionDetail>(`/v2/api/session/${sessionId}`, { fetch }),
		{ fallback: null }
	);
	return { session };
};
