export function formatNumber(n: number): string {
	if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
	if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
	return n.toString();
}

export function formatDurationMs(diffMs: number): string {
	if (diffMs < 0) return '';
	const secs = Math.floor(diffMs / 1000);
	if (secs < 60) return `${secs}s`;
	const mins = Math.floor(secs / 60);
	if (mins < 60) return `${mins}m ${secs % 60}s`;
	const hrs = Math.floor(mins / 60);
	const days = Math.floor(hrs / 24);
	if (days === 0) return `${hrs}h ${mins % 60}m`;
	return `${days}d ${hrs % 24}h`;
}

export function formatDuration(started: string | null, ended?: string | null): string {
	if (!started) return '';
	const start = new Date(started).getTime();
	const end = ended ? new Date(ended).getTime() : Date.now();
	const diffMs = end - start;
	if (diffMs < 0) return '';
	return formatDurationMs(diffMs);
}

export function formatRelativeTime(isoStr: string | null | undefined): string {
	if (!isoStr) return '—';
	const then = new Date(isoStr).getTime();
	const now = Date.now();
	const diffMs = now - then;
	if (diffMs < 0) return 'just now';

	const secs = Math.floor(diffMs / 1000);
	if (secs < 60) return 'just now';
	const mins = Math.floor(secs / 60);
	if (mins < 2) return '1 minute ago';
	if (mins < 60) return `${mins} minutes ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 2) return '1 hour ago';
	if (hrs < 24) return `${hrs} hours ago`;
	const days = Math.floor(hrs / 24);
	if (days < 2) return '1 day ago';
	if (days < 14) return `${days} days ago`;
	const weeks = Math.floor(days / 7);
	if (weeks < 5) return `${weeks} weeks ago`;
	const months = Math.floor(days / 30);
	if (months < 12) return `${months} months ago`;
	const years = Math.floor(days / 365);
	return `${years} years ago`;
}

export function formatRelativeTimeShort(isoStr: string | null | undefined): string {
	if (!isoStr) return '—';
	const then = new Date(isoStr).getTime();
	const now = Date.now();
	const diffMs = now - then;
	if (diffMs < 0) return 'now';

	const secs = Math.floor(diffMs / 1000);
	if (secs < 60) return 'now';
	const mins = Math.floor(secs / 60);
	if (mins < 60) return `${mins}m ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 24) return `${hrs}h ago`;
	const days = Math.floor(hrs / 24);
	if (days < 30) return `${days}d ago`;
	const months = Math.floor(days / 30);
	if (months < 12) return `${months}mo ago`;
	const years = Math.floor(days / 365);
	return `${years}y ago`;
}

export function formatFreshness(fetchedAt: string | null | undefined, intervalMinutes: number = 10): { label: string; state: 'fresh' | 'stale' | 'dead' } {
	if (!fetchedAt) return { label: 'No data', state: 'dead' };
	// Ensure the datetime is parsed as UTC. If the ISO string lacks a
	// timezone offset (e.g. a naive datetime from the backend), append 'Z'
	// so JavaScript doesn't interpret it as local time (causing a
	// persistent offset equal to the browser's UTC offset — e.g. 2 hours
	// for UTC+2).
	const normalized = /[+\-Z]\d{2}:?\d{2}$|Z$/i.test(fetchedAt) ? fetchedAt : fetchedAt + 'Z';
	const ageMs = Date.now() - new Date(normalized).getTime();
	const intervalMs = intervalMinutes * 60_000;
	if (ageMs <= intervalMs) return { label: `Updated ${formatRelativeTime(fetchedAt)}`, state: 'fresh' };
	if (ageMs <= intervalMs * 2) return { label: `Updated ${formatRelativeTime(fetchedAt)}`, state: 'stale' };
	return { label: `Updated ${formatRelativeTime(fetchedAt)}`, state: 'dead' };
}
