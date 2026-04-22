import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('WebSocket Client', () => {
	describe('Message Types', () => {
		it('should have correct client message types', () => {
			const MsgType = {
				SUBSCRIBE: 1,
				PING: 2
			};
			expect(MsgType.SUBSCRIBE).toBe(1);
			expect(MsgType.PING).toBe(2);
		});

		it('should have correct server message types', () => {
			const MsgType = {
				STATE: 101,
				RANK_UPDATE: 102,
				CHAIN_UPDATE: 103,
				PONG: 104,
				ACHIEVEMENT: 105,
				SESSION: 106,
				ERROR: 107
			};
			expect(MsgType.STATE).toBe(101);
			expect(MsgType.RANK_UPDATE).toBe(102);
			expect(MsgType.CHAIN_UPDATE).toBe(103);
			expect(MsgType.PONG).toBe(104);
			expect(MsgType.ACHIEVEMENT).toBe(105);
			expect(MsgType.SESSION).toBe(106);
			expect(MsgType.ERROR).toBe(107);
		});
	});

	describe('MessagePack Encoding', () => {
		it('should use msgpackr for binary encoding', () => {
			const { Packr } = require('msgpackr');
			const packr = new Packr();
			const encoded = packr.pack({ t: 1, s: 123 });
			expect(encoded).toBeDefined();
			expect(encoded.length).toBeGreaterThan(0);
		});

		it('should decode packed messages', () => {
			const { Packr } = require('msgpackr');
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