import type { PageLoad } from './$types';
import type { PlayerProfile } from '$lib/types';
import { apiFetch } from '$lib/api';
import { loadWithFallback } from '$lib/api-utils';

interface HistoryPoint {
	day: string;
	sp: number;
	pp: number;
}

interface HistoryResponse {
	user_id: string;
	window_days: number;
	series: HistoryPoint[];
}

interface AchievementEntry {
	key: string;
	name: string;
	description: string;
	icon: string;
	unlocked: boolean;
}

interface ExtendedPlayerProfile extends PlayerProfile {
	achievements?: AchievementEntry[];
}

export const load: PageLoad = async ({ params, fetch }) => {
	const userId = params.id;
	const [profile, history] = await Promise.all([
		loadWithFallback<ExtendedPlayerProfile | null>(
			() => apiFetch<ExtendedPlayerProfile>(`/api/player/${userId}`, { fetch }),
			{ fallback: null }
		),
		loadWithFallback<HistoryPoint[]>(
			async () => {
				const res = await apiFetch<HistoryResponse>(
					`/api/players/${userId}/history?window=30d`,
					{ fetch }
				);
				return res.series;
			},
			{ fallback: [] }
		)
	]);
	return { profile, history, achievements: profile?.achievements ?? [] };
};
