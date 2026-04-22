import type { PageLoad } from './$types';
import type { PlayerProfile } from '../../../app.d';

export const load: PageLoad = async ({ params, fetch }) => {
	const userId = params.id;

	try {
		const response = await fetch(`/v2/api/player/${userId}`);
		if (!response.ok) {
			return { profile: null };
		}
		const profile = (await response.json()) as PlayerProfile;
		return { profile };
	} catch {
		return { profile: null };
	}
};