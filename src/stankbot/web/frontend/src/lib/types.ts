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
	session_reactions?: number;
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
	reactions_in_chain?: number;
	reactions_in_session?: number;
	stanks_in_chain?: number;
	stanks_in_session?: number;
}

export interface PlayerProfile {
	user_id: string;
	display_name: string;
	discord_avatar: string | null;
	rank: number | null;
	stank_streak: { current: number; longest: number };
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
	achievements?: AchievementEntry[];
	last_stank_at: string | null;
}

export interface AchievementEntry {
	key: string;
	name: string;
	description: string;
	icon: string;
	unlocked: boolean;
}

export interface Badge {
	key: string;
	name: string;
	icon: string;
	description: string;
	unlocked_at: string;
}

export interface ChainMessageEntry {
	position: number;
	user_id: string;
	display_name: string;
	discord_avatar: string | null;
	created_at: string;
	sp_awarded: number;
}

export interface PlayerChainEntry {
	chain_id: number;
	started_at: string;
	broken_at: string | null;
	length: number;
	unique_contributors: number;
	user_stanks: number;
}

export interface ChainSummary {
	chain_id: number;
	session_id?: number | null;
	altar_name?: string;
	rolled_over?: boolean;
	started_at: string;
	broken_at: string | null;
	length: number;
	unique_contributors: number;
	starter_user_id: string | null;
	broken_by_user_id: string | null;
	contributors: [string, number][];
	total_reactions?: number;
	timeline?: ChainMessageEntry[];
	leaderboard?: PlayerRow[];
}

export interface SessionLeaderboardEntry {
	user_id: string;
	display_name: string;
	discord_avatar: string | null;
	earned_sp: number;
	punishments: number;
	net: number;
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
	total_sp?: number;
	total_pp?: number;
	session_leaderboard?: SessionLeaderboardEntry[];
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

// ---------------------------------------------------------------------------
// Media (Maphra)
// ---------------------------------------------------------------------------

export interface MediaItem {
	id: number;
	guild_id: string;
	media_type: string;
	external_id: string;
	slug: string | null;
	title: string;
	channel_name: string | null;
	channel_id: string | null;
	thumbnail_url: string | null;
	published_at: string | null;
	duration_seconds: number | null;
	added_by: string;
	metrics: Record<string, MediaMetricValue>;
	metrics_last_fetched_at: string | null;
	created_at: string | null;
	updated_at: string | null;
}

export interface MediaMetricValue {
	value: number;
	fetched_at: string;
}

export interface MetricSnapshot {
	fetched_at: string;
	value: number;
}

export interface MetricDef {
	key: string;
	label: string;
	format: string;
	icon: string;
}

export interface ProviderDef {
	type: string;
	label: string;
	icon: string;
	metrics: MetricDef[];
}

export interface CompareSeries {
	media_item_id: number;
	title: string;
	points: Array<{ x: string; y: number }>;
}

export interface CompareData {
	metric: MetricDef | null;
	series: CompareSeries[];
	aligned?: boolean;
}
