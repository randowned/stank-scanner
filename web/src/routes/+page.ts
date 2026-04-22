import { Packr } from 'msgpackr';
import type { PageLoad } from './$types';

const packr = new Packr();

const mockState = {
	guild_name: 'Test Server',
	stank_emoji: ':stank:',
	altar_sticker_url: '',
	current: 42,
	current_unique: 7,
	record: 89,
	record_unique: 12,
	alltime_record: 234,
	alltime_record_unique: 45,
	next_reset_at: new Date(Date.now() + 3600000).toISOString(),
	rankings: [
		{ user_id: 111, display_name: 'StankMaster', earned_sp: 15420, punishments: 120 },
		{ user_id: 222, display_name: 'ChainKing', earned_sp: 12300, punishments: 80 },
		{ user_id: 333, display_name: 'StreakLord', earned_sp: 9870, punishments: 50 },
		{ user_id: 444, display_name: 'QuickFinger', earned_sp: 7650, punishments: 200 },
		{ user_id: 555, display_name: 'LateStarter', earned_sp: 5430, punishments: 30 },
	],
	chain_starter: { user_id: 111, display_name: 'StankMaster', earned_sp: 15420, punishments: 120 },
	chainbreaker: { user_id: 444, display_name: 'QuickFinger', earned_sp: 7650, punishments: 200 }
};

export const load: PageLoad = async ({ fetch, url }) => {
	const devMode = url.searchParams.get('dev') === 'true';

	if (devMode) {
		return { state: mockState, guild_name: 'Test Server' };
	}

	try {
		const response = await fetch('/v2/api/board', {
			headers: {
				Accept: 'application/msgpack, application/json'
			}
		});
		if (!response.ok) {
			return { state: null, guild_name: 'StankBot' };
		}
		const contentType = response.headers.get('content-type') || '';
		let state;
		if (contentType.includes('msgpack')) {
			state = packr.unpack(new Uint8Array(await response.arrayBuffer()));
		} else {
			state = await response.json();
		}
		return { state, guild_name: state.guild_name || 'StankBot' };
	} catch {
		return { state: null, guild_name: 'StankBot' };
	}
};