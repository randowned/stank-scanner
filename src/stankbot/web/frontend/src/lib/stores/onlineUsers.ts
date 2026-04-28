import { writable } from 'svelte/store';

export interface OnlineUser {
	user_id: string;
	username: string;
	avatar_url: string;
	connected_at: string;
}

export const onlineUsers = writable<OnlineUser[]>([]);
