import { describe, it, expect, vi } from 'vitest';
import { formatDuration, formatDurationMs } from './format';

describe('formatDurationMs', () => {
	it('returns empty for negative diff', () => {
		expect(formatDurationMs(-1)).toBe('');
	});

	it('formats seconds (< 60s)', () => {
		expect(formatDurationMs(0)).toBe('0s');
		expect(formatDurationMs(1_000)).toBe('1s');
		expect(formatDurationMs(45_000)).toBe('45s');
		expect(formatDurationMs(59_000)).toBe('59s');
	});

	it('formats minutes and seconds (< 60m)', () => {
		expect(formatDurationMs(60_000)).toBe('1m 0s');
		expect(formatDurationMs(61_000)).toBe('1m 1s');
		expect(formatDurationMs(3_300_000)).toBe('55m 0s');
		expect(formatDurationMs(3_540_000)).toBe('59m 0s');
	});

	it('formats hours minutes seconds (< 24h)', () => {
		expect(formatDurationMs(3_600_000)).toBe('1h 0m 0s');
		expect(formatDurationMs(3_660_000)).toBe('1h 1m 0s');
		expect(formatDurationMs(3_661_000)).toBe('1h 1m 1s');
		expect(formatDurationMs(8_130_000)).toBe('2h 15m 30s');
		expect(formatDurationMs(86_399_000)).toBe('23h 59m 59s');
	});

	it('formats days hours minutes (>= 24h, no seconds)', () => {
		expect(formatDurationMs(86_400_000)).toBe('1d 0h 0m');
		expect(formatDurationMs(172_800_000)).toBe('2d 0h 0m');
		expect(formatDurationMs(259_200_000)).toBe('3d 0h 0m');
		expect(formatDurationMs(277_920_000)).toBe('3d 5h 12m');
		expect(formatDurationMs(1_800_000_000)).toBe('20d 20h 0m');
	});
});

describe('formatDuration', () => {
	it('returns empty for null start', () => {
		expect(formatDuration(null)).toBe('');
	});

	it('returns empty for negative diff (start > end)', () => {
		expect(formatDuration('2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z')).toBe('');
	});

	it('formats duration between two dates', () => {
		expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:00:45Z')).toBe('45s');
		expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:05:30Z')).toBe('5m 30s');
		expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T02:15:30Z')).toBe('2h 15m 30s');
		expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-03T05:12:00Z')).toBe('2d 5h 12m');
	});

	it('uses Date.now() when end is not provided', () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-01-01T00:05:00Z'));
		expect(formatDuration('2026-01-01T00:00:00Z')).toBe('5m 0s');
		vi.useRealTimers();
	});
});
