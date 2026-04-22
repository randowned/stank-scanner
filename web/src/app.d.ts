/// <reference types="@sveltejs/kit" />

declare global {
	namespace App {
		interface Locals {
			user: User | null;
		}
		interface PageData {
			user: User | null;
		}
	}
}

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

export interface BoardState {
	guild_name: string;
	stank_emoji: string;
	altar_sticker_url: string;
	current: number;
	current_unique: number;
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
	user_id: number;
	display_name: string;
	earned_sp: number;
	punishments: number;
}

export interface PlayerProfile {
	user_id: number;
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
	started_at: string;
	broken_at: string | null;
	length: number;
	unique_contributors: number;
	starter_user_id: number;
	broken_by_user_id: number | null;
	contributors: [number, number][];
}

export interface SessionSummary {
	session_id: number;
	started_at: string | null;
	ended_at: string | null;
	chains_started: number;
	chains_broken: number;
	top_earner: [number, number] | null;
	top_breaker: [number, number] | null;
}

export {};