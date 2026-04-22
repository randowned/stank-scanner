import { Packr } from 'msgpackr';
import { connectionStatus, wsLatency, boardState, addToast, type BoardState, type Badge, type ChainSummary, type SessionSummary } from './stores';
import { get } from 'svelte/store';

const packr = new Packr();

export const enum MsgType {
	SUBSCRIBE = 1,
	PING = 2,

	STATE = 101,
	RANK_UPDATE = 102,
	CHAIN_UPDATE = 103,
	PONG = 104,
	ACHIEVEMENT = 105,
	SESSION = 106,
	ERROR = 107
}

interface SubscribeMsg {
	t: typeof MsgType.SUBSCRIBE;
	s: number;
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

export function connect(guildId: number, userId: number): void {
	if (ws?.readyState === WebSocket.OPEN) {
		return;
	}

	connectionStatus.set('connecting');

	const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const host = window.location.host;
	const url = `${protocol}//${host}/v2/ws?guild_id=${guildId}&user_id=${userId}`;

	try {
		ws = new WebSocket(url);

		ws.binaryType = 'arraybuffer';

		ws.onopen = () => {
			connectionStatus.set('connected');
			reconnectAttempts = 0;

			subscribe(guildId);
			startPingLoop();
			addToast('Connected to live updates', 'success');
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
			connectionStatus.set('disconnected');
			stopPingLoop();

			if (event.code !== 1000) {
				attemptReconnect(guildId, userId);
			}
		};

		ws.onerror = (error) => {
			console.error('WebSocket error:', error);
			connectionStatus.set('error');
			addToast('Connection error', 'error');
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

function subscribe(guildId: number): void {
	if (ws?.readyState !== WebSocket.OPEN) {
		return;
	}

	const msg: SubscribeMsg = { t: MsgType.SUBSCRIBE, s: guildId };
	ws.send(packr.pack(msg));
}

function startPingLoop(): void {
	lastPingTime = Date.now();
	pingInterval = setInterval(() => {
		if (ws?.readyState !== WebSocket.OPEN) {
			return;
		}

		const msg: PingMsg = { t: MsgType.PING };
		ws.send(packr.pack(msg));
		lastPingTime = Date.now();
	}, 15000);
}

function stopPingLoop(): void {
	if (pingInterval) {
		clearInterval(pingInterval);
		pingInterval = null;
	}
}

function attemptReconnect(guildId: number, userId: number): void {
	if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
		addToast('Unable to reconnect. Please refresh.', 'error', 0);
		return;
	}

	reconnectAttempts++;
	const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);

	setTimeout(() => {
		const currentStatus = get(connectionStatus);
		if (currentStatus === 'disconnected' || currentStatus === 'error') {
			connect(guildId, userId);
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
			addToast(`Achievement unlocked: ${msg.d.badge.name}!`, 'success');
			break;

		case MsgType.SESSION:
			addToast(
				msg.d.action === 'start'
					? `Session ${msg.d.session_id} started`
					: `Session ${msg.d.session_id} ended`,
				'info'
			);
			break;

		case MsgType.ERROR:
			addToast(msg.d.message, 'error');
			break;
	}
}

export function isConnected(): boolean {
	return ws !== null && ws.readyState === WebSocket.OPEN;
}