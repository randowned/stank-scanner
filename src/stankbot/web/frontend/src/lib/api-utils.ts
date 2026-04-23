import { FetchError } from './api';

export interface LoadWithFallbackOptions<T> {
	/** Invoked when the fetcher throws. Use to log, report, or surface errors. */
	onError?: (error: unknown) => void;
	/** If set, only errors satisfying this predicate are swallowed; others re-throw. */
	shouldSwallow?: (error: unknown) => boolean;
	/** Value returned when the fetcher throws and the error is swallowed. */
	fallback: T;
}

/**
 * Wrap a load-function fetch so a failure produces a predictable fallback
 * instead of turning the page into a 500. Errors are logged by default;
 * pass `onError` to override (e.g. report to the toast store).
 *
 * Collapses the repeated `try { return await apiFetch(...) } catch { return fallback }`
 * pattern that lived at the top of every +page.ts.
 */
export async function loadWithFallback<T>(
	fetcher: () => Promise<T>,
	options: LoadWithFallbackOptions<T>
): Promise<T> {
	try {
		return await fetcher();
	} catch (err) {
		if (options.shouldSwallow && !options.shouldSwallow(err)) throw err;
		if (options.onError) options.onError(err);
		else logLoadError(err);
		return options.fallback;
	}
}

function logLoadError(err: unknown): void {
	if (err instanceof FetchError) {
		console.warn(`[load] ${err.status} ${err.code}: ${err.message}`);
	} else {
		console.warn('[load] unexpected error:', err);
	}
}
