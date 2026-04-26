import { base } from '$app/paths';
import { Packr } from 'msgpackr';
import { connectionStatus, wsLatency, boardState } from './stores/index';
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
	ERROR = 107,
	VERSION_MISMATCH = 108
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

type ServerMsg =
	| StateMsg
	| RankUpdateMsg
	| ChainUpdateMsg
	| PongMsg
	| AchievementMsg
	| SessionMsg
	| ErrorMsg
	| VersionMismatchMsg;

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
	}
}

export function isConnected(): boolean {
	return ws !== null && ws.readyState === WebSocket.OPEN;
}
