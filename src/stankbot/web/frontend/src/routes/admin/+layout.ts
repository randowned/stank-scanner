import { redirect } from '@sveltejs/kit';
import { base } from '$app/paths';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ parent }) => {
	const data = await parent();
	if (!data.user) throw redirect(303, '/auth/login');
	if (!data.is_admin) throw redirect(303, `${base}/`);
	return {};
};
