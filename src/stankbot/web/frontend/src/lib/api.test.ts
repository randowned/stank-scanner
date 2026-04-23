import { describe, it, expect, vi } from 'vitest';
import { apiFetch, apiPost, FetchError } from './api';
import { loadWithFallback } from './api-utils';

function mockFetch(responses: Array<Partial<Response> | Error>) {
	const calls: string[] = [];
	let i = 0;
	const fn = vi.fn(async (url: string) => {
		calls.push(String(url));
		const r = responses[Math.min(i, responses.length - 1)];
		i++;
		if (r instanceof Error) throw r;
		return r as Response;
	});
	return { fn, calls };
}

function jsonResponse(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

describe('api.ts', () => {
	it('apiFetch returns parsed JSON on 200', async () => {
		const { fn } = mockFetch([jsonResponse({ ok: true, n: 1 })]);
		const out = await apiFetch<{ ok: boolean; n: number }>('/api/x', {
			fetch: fn as unknown as typeof fetch
		});
		expect(out).toEqual({ ok: true, n: 1 });
	});

	it('apiFetch retries 5xx then succeeds', async () => {
		const { fn } = mockFetch([
			jsonResponse({}, 500),
			jsonResponse({}, 503),
			jsonResponse({ ok: true })
		]);
		const out = await apiFetch<{ ok: boolean }>('/api/x', {
			fetch: fn as unknown as typeof fetch
		});
		expect(out).toEqual({ ok: true });
		expect(fn).toHaveBeenCalledTimes(3);
	});

	it('apiFetch throws FetchError on 4xx immediately', async () => {
		const { fn } = mockFetch([
			new Response(JSON.stringify({ message: 'nope', code: 'not_allowed' }), {
				status: 403,
				headers: { 'content-type': 'application/json' }
			})
		]);
		await expect(
			apiFetch('/api/x', { fetch: fn as unknown as typeof fetch })
		).rejects.toMatchObject({
			name: 'FetchError',
			status: 403,
			code: 'not_allowed',
			message: 'nope'
		});
		expect(fn).toHaveBeenCalledTimes(1);
	});

	it('apiPost sends msgpack body by default in the browser', async () => {
		const fn = vi.fn(async (_url: string, init?: RequestInit) => {
			expect(init?.method).toBe('POST');
			const headers = new Headers(init?.headers);
			expect(headers.get('Content-Type')).toBe('application/msgpack');
			const body = init?.body as ArrayBuffer | Uint8Array | undefined;
			expect(body).toBeTruthy();
			expect((body as ArrayBuffer).byteLength ?? 0).toBeGreaterThan(0);
			return jsonResponse({ ok: true });
		});
		const out = await apiPost<{ ok: boolean }>('/api/x', { a: 1 }, {
			fetch: fn as unknown as typeof fetch
		});
		expect(out).toEqual({ ok: true });
	});

	it('apiPost honors forceJson to send JSON body', async () => {
		const fn = vi.fn(async (_url: string, init?: RequestInit) => {
			const headers = new Headers(init?.headers);
			expect(headers.get('Content-Type')).toBe('application/json');
			expect(init?.body).toBe(JSON.stringify({ a: 1 }));
			return jsonResponse({ ok: true });
		});
		const out = await apiPost<{ ok: boolean }>('/api/x', { a: 1 }, {
			fetch: fn as unknown as typeof fetch,
			forceJson: true
		});
		expect(out).toEqual({ ok: true });
	});

	it('FetchError is thrown instance', async () => {
		const { fn } = mockFetch([jsonResponse({ message: 'bad' }, 400)]);
		await expect(
			apiFetch('/api/x', { fetch: fn as unknown as typeof fetch })
		).rejects.toBeInstanceOf(FetchError);
	});
});

describe('loadWithFallback', () => {
	it('returns fetcher value on success', async () => {
		const out = await loadWithFallback<number>(async () => 42, { fallback: 0 });
		expect(out).toBe(42);
	});

	it('returns fallback on error and calls onError', async () => {
		const onError = vi.fn();
		const out = await loadWithFallback<number>(
			async () => {
				throw new Error('boom');
			},
			{ fallback: 99, onError }
		);
		expect(out).toBe(99);
		expect(onError).toHaveBeenCalledTimes(1);
	});

	it('re-throws when shouldSwallow returns false', async () => {
		await expect(
			loadWithFallback(
				async () => {
					throw new Error('nope');
				},
				{
					fallback: null,
					shouldSwallow: () => false
				}
			)
		).rejects.toThrow('nope');
	});
});
