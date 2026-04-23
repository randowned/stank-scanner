import { base } from '$app/paths';
import { Packr } from 'msgpackr';
import { connectionStatus, wsLatency, boardState } from './stores/index';
import { emitWsEvent } from './stores/ws-events';
import type { BoardState, Badge } from './types';
import { get } from 'svelte/store';

const packr = new Packr({ useRecords: false });

export enum MsgType {
	PING = 2,

	STATE = 101,
	RANK_UPDATE = 102,
	CHAIN_UPDATE = 103,
	PONG = 104,
	ACHIEVEMENT = 105,
	SESSION = 106,
	ERROR = 107
}

interface PingMsg {
	t: typeof MsgType.PING;
}

interface StateMsg {
	t: typeof MsgType.STATE;
	d: BoardState;
}

interface RankUpdateMsg {
	t: typeof MsgType.RANK_UPDATE;
	d: {
		rankings: BoardState['rankings'];
		updated_at: string;
	};
}

interface ChainUpdateMsg {
	t: typeof MsgType.CHAIN_UPDATE;
	d: {
		current: number;
		current_unique: number;
		starter_user_id: number | null;
	};
}

interface PongMsg {
	t: typeof MsgType.PONG;
}

interface AchievementMsg {
	t: typeof MsgType.ACHIEVEMENT;
	d: {
		user_id: number;
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

type ServerMsg = StateMsg | RankUpdateMsg | ChainUpdateMsg | PongMsg | AchievementMsg | SessionMsg | ErrorMsg;

let ws: WebSocket | null = null;
let pingInterval: ReturnType<typeof setInterval> | null = null;
let lastPingTime = 0;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 1000;

export function canConnect(): boolean {
	return typeof WebSocket !== 'undefined' && typeof window !== 'undefined';
}

function defaultUrl(): string {
	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const host = window.location.host;
	return `${protocol}//${host}${base}/ws`;
}

export function connect(url?: string): void {
	if (!canConnect()) return;
	if (ws?.readyState === WebSocket.OPEN) return;

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

			if (event.code !== 1000) {
				emitWsEvent({ kind: 'disconnected', code: event.code, reason: event.reason });
				attemptReconnect();
			}
		};

		ws.onerror = (error) => {
			console.error('[ws] error', error);
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
	if (ws) {
		ws.close(1000, 'Client disconnect');
		ws = null;
	}
	connectionStatus.set('disconnected');
}

function _sendPacked(msg: PingMsg): void {
	if (ws?.readyState !== WebSocket.OPEN) {
		return;
	}
	const packed = packr.pack(msg) as Uint8Array;
	const buf = packed.buffer.slice(
		packed.byteOffset,
		packed.byteOffset + packed.byteLength,
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
	if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
		emitWsEvent({ kind: 'reconnect-failed' });
		return;
	}

	reconnectAttempts++;
	const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);

	setTimeout(() => {
		const currentStatus = get(connectionStatus);
		if (currentStatus === 'disconnected' || currentStatus === 'error') {
			connect();
		}
	}, delay);
}

function handleMessage(msg: ServerMsg): void {
	switch (msg.t) {
		case MsgType.STATE:
			boardState.set(msg.d);
			break;

		case MsgType.RANK_UPDATE:
			boardState.update((state) => {
				if (state) {
					return { ...state, rankings: msg.d.rankings };
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
	}
}

export function isConnected(): boolean {
	return ws !== null && ws.readyState === WebSocket.OPEN;
}
