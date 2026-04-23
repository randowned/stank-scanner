import { redirect } from '@sveltejs/kit';
import { base } from '$app/paths';

export const prerender = false;

export function load() {
	throw redirect(308, `${base}/admin/admins`);
}
