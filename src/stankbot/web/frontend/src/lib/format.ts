export function formatNumber(n: number): string {
	if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
	if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
	return n.toString();
}

export function formatDuration(started: string | null, ended?: string | null): string {
	if (!started) return '';
	const start = new Date(started).getTime();
	const end = ended ? new Date(ended).getTime() : Date.now();
	const diffMs = end - start;
	if (diffMs < 0) return '';
	const mins = Math.floor(diffMs / 60000);
	if (mins < 1) return '< 1m';
	if (mins < 60) return `${mins}m`;
	const hrs = Math.floor(mins / 60);
	const rem = mins % 60;
	return rem > 0 ? `${hrs}h ${rem}m` : `${hrs}h`;
}
