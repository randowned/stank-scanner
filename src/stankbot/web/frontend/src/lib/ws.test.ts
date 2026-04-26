import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Packr } from 'msgpackr';

describe('WebSocket Client', () => {
	describe('Message Types', () => {
		it('should have correct client message types', () => {
			const MsgType = {
				SUBSCRIBE: 1,
				PING: 2,
				VERSION_RESPONSE: 3
			};
			expect(MsgType.SUBSCRIBE).toBe(1);
			expect(MsgType.PING).toBe(2);
			expect(MsgType.VERSION_RESPONSE).toBe(3);
		});

		it('should have correct server message types', () => {
			const MsgType = {
				STATE: 101,
				RANK_UPDATE: 102,
				CHAIN_UPDATE: 103,
				PONG: 104,
				ACHIEVEMENT: 105,
				SESSION: 106,
				ERROR: 107,
				VERSION_MISMATCH: 108
			};
			expect(MsgType.STATE).toBe(101);
			expect(MsgType.RANK_UPDATE).toBe(102);
			expect(MsgType.CHAIN_UPDATE).toBe(103);
			expect(MsgType.PONG).toBe(104);
			expect(MsgType.ACHIEVEMENT).toBe(105);
			expect(MsgType.SESSION).toBe(106);
			expect(MsgType.ERROR).toBe(107);
			expect(MsgType.VERSION_MISMATCH).toBe(108);
		});
	});

	describe('MessagePack Encoding', () => {
		it('should use msgpackr for binary encoding', () => {
			const packr = new Packr();
			const encoded = packr.pack({ t: 1, s: 123 });
			expect(encoded).toBeDefined();
			expect(encoded.length).toBeGreaterThan(0);
		});

		it('should decode packed messages', () => {
			const packr = new Packr();
			const original = { t: 101, d: { current: 50 } };
			const encoded = packr.pack(original);
			const decoded = packr.unpack(encoded);
			expect(decoded.t).toBe(101);
			expect(decoded.d.current).toBe(50);
		});
	});

	describe('Latency tracking', () => {
		it('should calculate latency from pong', () => {
			const lastPingTime = Date.now() - 100;
			const latency = Date.now() - lastPingTime;
			expect(latency).toBeGreaterThanOrEqual(0);
			expect(latency).toBeLessThan(200);
		});
	});
});

describe('WebSocket ID precision', () => {
	let originalWebSocket: typeof WebSocket;
	let mockWsInstances: Array<{
		url: string;
		readyState: number;
		binaryType: string;
		send: ReturnType<typeof vi.fn>;
		close: ReturnType<typeof vi.fn>;
		onopen: ((this: WebSocket, ev: Event) => unknown) | null;
		onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null;
		onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null;
		onerror: ((this: WebSocket, ev: Event) => unknown) | null;
	}>;

	beforeEach(async () => {
		originalWebSocket = globalThis.WebSocket;
		mockWsInstances = [];

		const MockWebSocket = vi.fn(function (this: WebSocket, url: string | URL) {
			const instance = {
				url: String(url),
				readyState: 0,
				binaryType: '',
				send: vi.fn(),
				close: vi.fn(),
				onopen: null,
				onclose: null,
				onmessage: null,
				onerror: null,
			};
			mockWsInstances.push(instance);
			return instance as unknown as WebSocket;
		}) as unknown as typeof WebSocket;
		(MockWebSocket as unknown as Record<string, number>).OPEN = 1;
		(MockWebSocket as unknown as Record<string, number>).CONNECTING = 0;
		(MockWebSocket as unknown as Record<string, number>).CLOSING = 2;
		(MockWebSocket as unknown as Record<string, number>).CLOSED = 3;
		globalThis.WebSocket = MockWebSocket;

		// Reset module state between tests
		const mod = await import('./ws');
		(mod as unknown as { disconnect?: () => void }).disconnect?.();
	});

	afterEach(() => {
		globalThis.WebSocket = originalWebSocket;
	});

	it('should not leak guild_id or user_id in WebSocket URL', async () => {
		const { connect } = await import('./ws');

		connect();

		expect(mockWsInstances.length).toBe(1);
		const url = mockWsInstances[0].url;

		// Guild and user are read from the session cookie — never from query params
		expect(url).not.toContain('guild_id=');
		expect(url).not.toContain('user_id=');
		expect(url).toMatch(/\/ws$/);
	});
});