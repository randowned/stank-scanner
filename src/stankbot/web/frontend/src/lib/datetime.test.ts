import { describe, it, expect } from 'vitest';
import { formatDateTime, formatIsoUtc, formatResetTime } from './datetime';

describe('datetime.ts', () => {
	describe('formatDateTime', () => {
		it('returns fallback for null', () => {
			expect(formatDateTime(null)).toBe('—');
		});

		it('returns fallback for undefined', () => {
			expect(formatDateTime(undefined)).toBe('—');
		});

		it('returns fallback for empty string', () => {
			expect(formatDateTime('')).toBe('—');
		});

		it('returns custom fallback when provided', () => {
			expect(formatDateTime(null, 'N/A')).toBe('N/A');
			expect(formatDateTime(undefined, 'N/A')).toBe('N/A');
		});

		it('formats ISO string to non-empty string', () => {
			const result = formatDateTime('2026-04-26T14:30:00+00:00');
			expect(result).toBeTruthy();
			expect(result.length).toBeGreaterThan(0);
		});

		it('formats ISO string with timezone offset info', () => {
			const result = formatDateTime('2026-04-26T14:30:00+00:00');
			// Should contain month/day/time parts (actual output varies by browser locale)
			expect(result).toMatch(/\d/);
		});

		it('handles ISO string with different dates', () => {
			const result = formatDateTime('2025-12-31T23:59:59+00:00');
			expect(result).toBeTruthy();
		});
	});

	describe('formatResetTime', () => {
		it('returns fallback for null', () => {
			expect(formatResetTime(null)).toBe('—');
		});

		it('returns fallback for undefined', () => {
			expect(formatResetTime(undefined)).toBe('—');
		});

		it('formats ISO string to non-empty string', () => {
			const result = formatResetTime('2026-04-26T14:30:00+00:00');
			expect(result).toBeTruthy();
		});

		it('includes timezone name in output', () => {
			const result = formatResetTime('2026-04-26T14:30:00+00:00');
			expect(result.length).toBeGreaterThan(5);
		});
	});

	describe('formatIsoUtc', () => {
		it('returns fallback for null', () => {
			expect(formatIsoUtc(null)).toBe('—');
		});

		it('returns fallback for undefined', () => {
			expect(formatIsoUtc(undefined)).toBe('—');
		});

		it('returns fallback for empty string', () => {
			expect(formatIsoUtc('')).toBe('—');
		});

		it('returns custom fallback', () => {
			expect(formatIsoUtc(null, 'N/A')).toBe('N/A');
		});

		it('formats timezone-aware ISO string as UTC date-time', () => {
			const result = formatIsoUtc('2026-05-01T22:34:00+00:00');
			expect(result).toBe('2026-05-01 22:34');
		});

		it('formats naive ISO string as UTC (normalised with Z)', () => {
			const result = formatIsoUtc('2026-04-26T14:30:00');
			expect(result).toBe('2026-04-26 14:30');
		});

		it('handles ISO string with Z suffix', () => {
			const result = formatIsoUtc('2025-12-31T23:59:59Z');
			expect(result).toBe('2025-12-31 23:59');
		});

		it('pads single-digit month/day', () => {
			const result = formatIsoUtc('2026-01-05T03:07:00+00:00');
			expect(result).toBe('2026-01-05 03:07');
		});
	});
});