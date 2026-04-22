import type { PageLoad } from './$types';
import type { SessionSummary } from '../../app.d';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const response = await fetch('/v2/api/sessions');
		if (!response.ok) {
			return { sessions: [] };
		}
		const sessions = (await response.json()) as SessionSummary[];
		return { sessions };
	} catch {
		return { sessions: [] };
	}
};