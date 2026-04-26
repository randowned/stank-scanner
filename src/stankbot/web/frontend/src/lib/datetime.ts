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