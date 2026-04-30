export function formatNumber(n: number): string {
	if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
	if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
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
