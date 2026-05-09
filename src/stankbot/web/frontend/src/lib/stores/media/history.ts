import { writable } from 'svelte/store';
import type { MetricSnapshot, CompareData } from '$lib/types';

/** Cached chart data per `${mediaId}:${metric}:${hours}:${aggregation}:${mode}:${compareIds}` key. */
export const mediaHistoryCache = writable<Record<string, {
	history: MetricSnapshot[];
	compare?: CompareData | null;
}>>({});
