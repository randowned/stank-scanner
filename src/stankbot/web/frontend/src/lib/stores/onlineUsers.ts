import { writable } from 'svelte/store';

export interface OnlineUser {
	user_id: string;
	username: string;
	discord_avatar: string;
	connected_at: string;
	is_admin: boolean;
}

export const onlineUsers = writable<OnlineUser[]>([]);
