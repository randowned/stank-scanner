const DEFAULT_FORMAT: Intl.DateTimeFormatOptions = {
	month: 'short',
	day: 'numeric',
	hour: 'numeric',
	minute: '2-digit'
};

const DATE_FORMATTER = new Intl.DateTimeFormat('en-US', DEFAULT_FORMAT);

const RESET_FORMATTER = new Intl.DateTimeFormat('en-US', {
	...DEFAULT_FORMAT,
	timeZoneName: 'short'
});

export function formatDateTime(
	isoStr: string | null | undefined,
	fallback = '—'
): string {
	if (!isoStr) return fallback;
	return DATE_FORMATTER.format(new Date(isoStr));
}

export function formatResetTime(isoStr: string | null | undefined): string {
	if (!isoStr) return '—';
	return RESET_FORMATTER.format(new Date(isoStr));
}

export function formatIsoUtc(isoStr: string | null | undefined, fallback = '—'): string {
	if (!isoStr) return fallback;
	const normalized = /[+\-Z]\d{2}:?\d{2}$|Z$/i.test(isoStr) ? isoStr : isoStr + 'Z';
	const d = new Date(normalized);
	const Y = d.getUTCFullYear();
	const M = String(d.getUTCMonth() + 1).padStart(2, '0');
	const D = String(d.getUTCDate()).padStart(2, '0');
	const h = String(d.getUTCHours()).padStart(2, '0');
	const m = String(d.getUTCMinutes()).padStart(2, '0');
	return `${Y}-${M}-${D} ${h}:${m}`;
}