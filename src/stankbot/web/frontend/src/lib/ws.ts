import { base } from '$app/paths';
import { Packr } from 'msgpackr';
import { connectionStatus, wsLatency, boardState, onlineUsers } from './stores/index';
import type { OnlineUser } from './stores/index';
import { mediaMetricUpdates } from './stores/index';
import type { MediaMetricUpdate } from './stores/index';
import { ownerMetricUpdates } from './stores/index';
import type { OwnerMetricUpdate } from './stores/index';
import { emitWsEvent } from './stores/ws-events';
import type { BoardState, Badge } from './types';
import { get } from 'svelte/store';

const packr = new Packr({ useRecords: false });

const VERSION_KEY = 'stankbot:version';

export enum MsgType {
	PING = 2,
	VERSION_RESPONSE = 3,

	STATE = 101,
	RANK_UPDATE = 102,
	CHAIN_UPDATE = 103,
	PONG = 104,
	ACHIEVEMENT = 105,
	SESSION = 106,
	GAME_EVENT = 107,
	ERROR = 108,
	VERSION_MISMATCH = 109,
	ONLINE_USERS = 110,
	MEDIA_SNAPSHOT = 111,
	MEDIA_MILESTONE = 112,
	OWNER_SNAPSHOT = 113,
	OWNER_MILESTONE = 114
}

interface PingMsg {
	t: typeof MsgType.PING;
}

interface VersionResponseMsg {
	t: typeof MsgType.VERSION_RESPONSE;
	d: { version: string };
}

interface StateMsg {
	t: typeof MsgType.STATE;
	d: BoardState & { version?: string };
}

interface RankUpdateMsg {
	t: typeof MsgType.RANK_UPDATE;
	d: {
		rankings: BoardState['rankings'];
		reactions?: number;
		session_reactions?: number;
		updated_at: string;
	};
}

interface ChainUpdateMsg {
	t: typeof MsgType.CHAIN_UPDATE;
	d: {
		current: number;
		current_unique: number;
		starter_user_id: string | null;
	};
}

interface PongMsg {
	t: typeof MsgType.PONG;
}

interface AchievementMsg {
	t: typeof MsgType.ACHIEVEMENT;
	d: {
		user_id: string;
		badge: Badge;
	};
}

export interface GameEventData {
	id: number;
	type: string;
	user_id: string | null;
	user_name: string | null;
	delta: number;
	reason: string | null;
	created_at: string | null;
}

interface GameEventMsg {
	t: typeof MsgType.GAME_EVENT;
	d: GameEventData;
}

interface SessionMsg {
	t: typeof MsgType.SESSION;
	d: {
		session_id: number;
		action: 'start' | 'end';
		started_at: string;
		ended_at: string | null;
	};
}

interface ErrorMsg {
	t: typeof MsgType.ERROR;
	d: {
		code: string;
		message: string;
	};
}

interface VersionMismatchMsg {
	t: typeof MsgType.VERSION_MISMATCH;
	d: {
		server_version: string;
		client_version: string;
	};
}

interface OnlineUsersMsg {
	t: typeof MsgType.ONLINE_USERS;
	d: {
		users: OnlineUser[];
	};
}

interface MediaSnapshotMsg {
	t: typeof MsgType.MEDIA_SNAPSHOT;
	d: {
		media_item_id: number;
		metric_key: string;
		value: number;
		fetched_at: string;
	};
}

interface MediaMilestoneMsg {
	t: typeof MsgType.MEDIA_MILESTONE;
	d: {
		media_item_id: number;
		media_type: string;
		metric_key: string;
		milestone_value: number;
		new_value: number;
		title: string;
		channel_name: string | null;
		thumbnail_url: string | null;
		name: string | null;
		external_id: string;
	};
}

interface OwnerSnapshotMsg {
	t: typeof MsgType.OWNER_SNAPSHOT;
	d: {
		owner_id: number;
		media_type: string;
		metric_key: string;
		value: number;
	};
}

interface OwnerMilestoneMsg {
	t: typeof MsgType.OWNER_MILESTONE;
	d: {
		owner_id: number;
		owner_name: string;
		media_type: string;
		metric_key: string;
		milestone_value: number;
		new_value: number;
		thumbnail_url: string | null;
		external_url: string | null;
	};
}

type ServerMsg =
	| StateMsg
	| RankUpdateMsg
	| ChainUpdateMsg
	| PongMsg
	| AchievementMsg
	| SessionMsg
	| GameEventMsg
	| ErrorMsg
	| VersionMismatchMsg
	| OnlineUsersMsg
	| MediaSnapshotMsg
	| MediaMilestoneMsg
	| OwnerSnapshotMsg
	| OwnerMilestoneMsg;

let ws: WebSocket | null = null;
let pingInterval: ReturnType<typeof setInterval> | null = null;
let lastPingTime = 0;
let reconnectAttempts = 0;
let intentionalClose = false;
const RECONNECT_DELAY = 1000;
const MAX_BACKOFF = 30000;

export function canConnect(): boolean {
	return typeof WebSocket !== 'undefined' && typeof window !== 'undefined';
}

function defaultUrl(): string {
	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const host = window.location.host;
	return `${protocol}//${host}${base}/ws`;
}

export function getStoredVersion(): string {
	try {
		return localStorage.getItem(VERSION_KEY) ?? '';
	} catch {
		return '';
	}
}

export function setStoredVersion(version: string): void {
	try {
		if (version) localStorage.setItem(VERSION_KEY, version);
	} catch {
		// localStorage unavailable — ignore
	}
}

export function connect(url?: string): void {
	if (!canConnect()) return;
	if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;

	intentionalClose = false;
	connectionStatus.set('connecting');

	const target = url ?? defaultUrl();
	console.log('[ws] connecting to', target);

	try {
		ws = new WebSocket(target);

		ws.binaryType = 'arraybuffer';

		ws.onopen = () => {
			console.log('[ws] connected');
			connectionStatus.set('connected');
			reconnectAttempts = 0;

			startPingLoop();
			emitWsEvent({ kind: 'connected' });
		};

		ws.onmessage = (event) => {
			try {
				const data = new Uint8Array(event.data);
				const msg = packr.unpack(data) as ServerMsg;
				handleMessage(msg);
			} catch (err) {
				console.error('Failed to parse message:', err);
			}
		};

		ws.onclose = (event) => {
			console.log('[ws] closed', event.code, event.reason);
			connectionStatus.set('disconnected');
			stopPingLoop();

			if (event.code !== 1000 && !intentionalClose) {
				emitWsEvent({ kind: 'disconnected', code: event.code, reason: event.reason });
				attemptReconnect();
			}
			intentionalClose = false;
		};

		ws.onerror = (error) => {
			if (!intentionalClose) {
				console.error('[ws] error', error);
			}
			connectionStatus.set('error');
			emitWsEvent({ kind: 'error', code: 'ws_error', message: 'Connection error' });
		};
	} catch (err) {
		console.error('Failed to connect:', err);
		connectionStatus.set('error');
	}
}

export function disconnect(): void {
	stopPingLoop();
	intentionalClose = true;
	if (ws) {
		ws.close(1000, 'Client disconnect');
		ws = null;
	}
	connectionStatus.set('disconnected');
}

function _sendPacked(msg: PingMsg | VersionResponseMsg): void {
	if (ws?.readyState !== WebSocket.OPEN) {
		return;
	}
	const packed = packr.pack(msg) as Uint8Array;
	const buf = packed.buffer.slice(
		packed.byteOffset,
		packed.byteOffset + packed.byteLength
	) as ArrayBuffer;
	ws.send(buf);
}

function startPingLoop(): void {
	lastPingTime = Date.now();
	pingInterval = setInterval(() => {
		_sendPacked({ t: MsgType.PING });
		lastPingTime = Date.now();
	}, 15000);
}

function stopPingLoop(): void {
	if (pingInterval) {
		clearInterval(pingInterval);
		pingInterval = null;
	}
}

function attemptReconnect(): void {
	reconnectAttempts++;
	const delay = Math.min(RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1), MAX_BACKOFF);

	setTimeout(() => {
		const currentStatus = get(connectionStatus);
		if (currentStatus === 'disconnected' || currentStatus === 'error') {
			connect();
		}
	}, delay);
}

function handleMessage(msg: ServerMsg): void {
	switch (msg.t) {
		case MsgType.STATE: {
			boardState.set(msg.d);
			const serverVersion = msg.d.version;
			if (serverVersion) {
				const clientVersion = getStoredVersion();
				_sendPacked({ t: MsgType.VERSION_RESPONSE, d: { version: clientVersion } });
			}
			break;
		}

		case MsgType.RANK_UPDATE:
			boardState.update((state) => {
				if (state) {
					const patch: Partial<BoardState> = { rankings: msg.d.rankings };
					if (msg.d.reactions !== undefined) patch.reactions = msg.d.reactions;
					if (msg.d.session_reactions !== undefined) patch.session_reactions = msg.d.session_reactions;
					return { ...state, ...patch };
				}
				return state;
			});
			break;

		case MsgType.CHAIN_UPDATE:
			boardState.update((state) => {
				if (state) {
					return {
						...state,
						current: msg.d.current,
						current_unique: msg.d.current_unique
					};
				}
				return state;
			});
			break;

		case MsgType.PONG:
			wsLatency.set(Date.now() - lastPingTime);
			break;

		case MsgType.ACHIEVEMENT:
			emitWsEvent({ kind: 'achievement', userId: msg.d.user_id, badge: msg.d.badge });
			break;

		case MsgType.GAME_EVENT:
			for (const cb of gameEventCallbacks) {
				cb(msg.d);
			}
			break;

		case MsgType.SESSION:
			emitWsEvent({ kind: 'session', action: msg.d.action, sessionId: msg.d.session_id });
			break;

		case MsgType.ERROR:
			emitWsEvent({ kind: 'error', code: msg.d.code, message: msg.d.message });
			break;

		case MsgType.VERSION_MISMATCH:
			setStoredVersion(msg.d.server_version);
			emitWsEvent({
				kind: 'update-available',
				serverVersion: msg.d.server_version,
				clientVersion: msg.d.client_version
			});
			break;

		case MsgType.ONLINE_USERS:
			onlineUsers.set(msg.d.users);
			break;

		case MsgType.MEDIA_SNAPSHOT: {
			const update: MediaMetricUpdate = {
				mediaItemId: msg.d.media_item_id,
				metricKey: msg.d.metric_key,
				value: msg.d.value,
				fetchedAt: msg.d.fetched_at
			};
			mediaMetricUpdates.set([update]);
			break;
		}

		case MsgType.MEDIA_MILESTONE:
			emitWsEvent({
				kind: 'media-milestone',
				mediaItemId: msg.d.media_item_id,
				title: msg.d.title,
				metricKey: msg.d.metric_key,
				milestoneValue: msg.d.milestone_value,
				newValue: msg.d.new_value,
				thumbnailUrl: msg.d.thumbnail_url,
				name: msg.d.name
			});
			break;

		case MsgType.OWNER_SNAPSHOT: {
			const update: OwnerMetricUpdate = {
				ownerId: msg.d.owner_id,
				metrics: [{ key: msg.d.metric_key, value: msg.d.value, fetchedAt: '' }]
			};
			ownerMetricUpdates.set(update);
			break;
		}

		case MsgType.OWNER_MILESTONE:
			emitWsEvent({
				kind: 'owner-milestone',
				ownerId: msg.d.owner_id,
				ownerName: msg.d.owner_name,
				mediaType: msg.d.media_type,
				metricKey: msg.d.metric_key,
				milestoneValue: msg.d.milestone_value,
				newValue: msg.d.new_value,
				thumbnailUrl: msg.d.thumbnail_url,
				externalUrl: msg.d.external_url
			});
			break;
	}
}

export function isConnected(): boolean {
	return ws !== null && ws.readyState === WebSocket.OPEN;
}

// ---- Game event callbacks (for live events page) -----------------------

type GameEventCallback = (event: GameEventData) => void;
let gameEventCallbacks: GameEventCallback[] = [];

export function onGameEvent(cb: GameEventCallback): () => void {
	gameEventCallbacks.push(cb);
	return () => {
		gameEventCallbacks = gameEventCallbacks.filter((c) => c !== cb);
	};
}
