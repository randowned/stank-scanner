import { Packr } from 'msgpackr';
import { beginRequest, endRequest } from '$lib/stores/loading';

export const API_BASE = '/api';

const packr = new Packr({ useRecords: false });

export interface ApiError {
	status: number;
	code: string;
	message: string;
}

export class FetchError extends Error {
	readonly status: number;
	readonly code: string;
	constructor(error: ApiError) {
		super(error.message);
		this.name = 'FetchError';
		this.status = error.status;
		this.code = error.code;
	}
}

interface RequestOptions {
	fetch?: typeof fetch;
	init?: RequestInit;
	/** retry 5xx responses (default: 2 retries with 250ms / 750ms backoff) */
	retry?: boolean;
	/** force JSON request body even in the browser (default: msgpack in browser) */
	forceJson?: boolean;
}

const RETRY_DELAYS_MS = [250, 750];

function resolveUrl(path: string): string {
	if (/^https?:/.test(path)) return path;
	if (path.startsWith('/')) return path;
	return `${API_BASE}/${path}`;
}

async function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

async function parseError(response: Response): Promise<ApiError> {
	let message = response.statusText || `HTTP ${response.status}`;
	let code = 'http_error';
	try {
		const body = await response.clone().json();
		if (body && typeof body === 'object') {
			if (typeof body.message === 'string') message = body.message;
			if (typeof body.code === 'string') code = body.code;
			else if (typeof body.detail === 'string') message = body.detail;
		}
	} catch {
		// response body was not JSON — keep the defaults
	}
	return { status: response.status, code, message };
}

async function unpackBody<T>(response: Response): Promise<T> {
	// Read content-type defensively: during SvelteKit SSR the wrapped
	// Response hides arbitrary headers unless they're whitelisted via
	// `filterSerializedResponseHeaders`, and calling .get() on a filtered
	// header throws. Fall back to JSON when the header isn't accessible —
	// the main path (browser fetch) still gets msgpack negotiation.
	let contentType: string;
	try {
		contentType = response.headers.get('content-type') || '';
	} catch {
		contentType = '';
	}
	if (contentType.includes('msgpack')) {
		const buf = new Uint8Array(await response.arrayBuffer());
		return packr.unpack(buf) as T;
	}
	return (await response.json()) as T;
}

async function request<T>(
	method: string,
	path: string,
	body: unknown,
	options: RequestOptions = {}
): Promise<T> {
	const customFetch = options.fetch ?? fetch;
	const url = resolveUrl(path);
	const shouldRetry = options.retry ?? (method === 'GET');
	const attempts = shouldRetry ? RETRY_DELAYS_MS.length + 1 : 1;

	const headers = new Headers(options.init?.headers);
	if (!headers.has('Accept')) {
		// Only negotiate msgpack in the browser — during SSR SvelteKit filters
		// the content-type header off the wrapped Response, which would make
		// us unable to distinguish msgpack from JSON.
		const canNegotiateMsgpack = typeof window !== 'undefined';
		headers.set(
			'Accept',
			canNegotiateMsgpack ? 'application/msgpack, application/json' : 'application/json'
		);
	}

	let init: RequestInit = { ...options.init, method, headers };
	if (body !== undefined) {
		const useMsgpack = typeof window !== 'undefined' && !options.forceJson;
		if (useMsgpack) {
			if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/msgpack');
			const packed = packr.pack(body) as Uint8Array;
			const buf = packed.buffer.slice(
				packed.byteOffset,
				packed.byteOffset + packed.byteLength
			) as ArrayBuffer;
			init = { ...init, body: buf };
		} else {
			if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
			init = { ...init, body: JSON.stringify(body) };
		}
	}

	const trackLoading = typeof window !== 'undefined';
	if (trackLoading) beginRequest();
	try {
		let lastError: unknown;
		for (let attempt = 0; attempt < attempts; attempt++) {
			try {
				const response = await customFetch(url, init);
				if (response.ok) return await unpackBody<T>(response);
				if (response.status < 500 || attempt === attempts - 1) {
					throw new FetchError(await parseError(response));
				}
				lastError = new FetchError(await parseError(response));
			} catch (err) {
				lastError = err;
				if (attempt === attempts - 1) throw err;
				if (err instanceof FetchError && err.status < 500) throw err;
			}
			await sleep(RETRY_DELAYS_MS[attempt]);
		}
		throw lastError ?? new Error('unreachable');
	} finally {
		if (trackLoading) endRequest();
	}
}

export function apiFetch<T>(path: string, options?: RequestOptions): Promise<T> {
	return request<T>('GET', path, undefined, options);
}

export function apiPost<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
	return request<T>('POST', path, body ?? {}, options);
}

export function apiDelete<T>(path: string, options?: RequestOptions): Promise<T> {
	return request<T>('DELETE', path, undefined, options);
}
