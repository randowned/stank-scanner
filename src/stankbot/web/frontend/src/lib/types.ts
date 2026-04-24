/**
 * Domain types for the StankBot v2 dashboard.
 *
 * Discord snowflake IDs are represented as strings to preserve precision
 * (JS Number loses accuracy above 2^53 — see v2.3.2 / v2.3.3 history).
 * Branded aliases let call sites opt into stricter checks incrementally
 * without forcing a repo-wide rewrite.
 */

// Branded IDs — plain strings at runtime, distinct at compile time.
export type UserId = string & { readonly __brand: 'UserId' };
export type GuildId = string & { readonly __brand: 'GuildId' };
export type ChainId = number & { readonly __brand: 'ChainId' };
export type SessionId = number & { readonly __brand: 'SessionId' };

export const asUserId = (v: string | number): UserId => String(v) as UserId;
export const asGuildId = (v: string | number): GuildId => String(v) as GuildId;
export const asChainId = (v: number): ChainId => v as ChainId;
export const asSessionId = (v: number): SessionId => v as SessionId;

export interface User {
	id: string;
	username: string;
	avatar: string | null;
}

export interface Guild {
	id: string;
	name: string;
	icon: string | null;
}

export interface GuildInfo {
	id: string;
	name: string;
	icon_url: string | null;
	bot_present: boolean;
	is_admin: boolean;
	is_owner: boolean;
	is_active: boolean;
}

export interface BoardState {
	guild_name: string;
	stank_emoji: string;
	altar_sticker_url: string;
	session_id?: number | null;
	current: number;
	current_unique: number;
	reactions: number;
	chain_length?: number;
	record: number;
	record_unique: number;
	alltime_record: number;
	alltime_record_unique: number;
	next_reset_at: string | null;
	rankings: PlayerRow[];
	chain_starter: PlayerRow | null;
	chainbreaker: PlayerRow | null;
}

export interface PlayerRow {
	user_id: string;
	display_name: string;
	discord_avatar?: string | null;
	earned_sp: number;
	punishments: number;
	net?: number;
	reactions_in_session?: number;
	stanks_in_session?: number;
}

export interface PlayerProfile {
	user_id: string;
	display_name: string;
	session: {
		earned_sp: number;
		punishments: number;
		net: number;
	};
	alltime: {
		earned_sp: number;
		punishments: number;
		chains_started: number;
		chains_broken: number;
	};
	badges: Badge[];
	last_stank_at: string | null;
}

export interface Badge {
	key: string;
	name: string;
	icon: string;
	description: string;
	unlocked_at: string;
}

export interface ChainSummary {
	chain_id: number;
	session_id?: number | null;
	started_at: string;
	broken_at: string | null;
	length: number;
	unique_contributors: number;
	starter_user_id: string | null;
	broken_by_user_id: string | null;
	contributors: [string, number][];
	total_reactions?: number;
	leaderboard?: PlayerRow[];
}

export interface SessionSummary {
	session_id: number;
	started_at: string | null;
	ended_at?: string | null;
	active?: boolean;
	chains_started?: number;
	chains_broken?: number;
	unique_stankers?: number;
	stanks?: number;
	chains?: number;
	reactions?: number;
	top_earner?: [string, number] | null;
	top_breaker?: [string, number] | null;
}

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface Toast {
	id: string;
	message: string;
	type: ToastKind;
	duration?: number;
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
