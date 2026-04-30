<script lang="ts">
	import type { CompareData } from '$lib/types';
	import { formatNumber } from '$lib/format';

	interface Props {
		compareData: CompareData;
		width?: number;
		height?: number;
	}

	let { compareData, width = 600, height = 200 }: Props = $props();

	const COLORS = [
		'#3b82f6', '#ef4444', '#22c55e', '#a855f7',
		'#f97316', '#14b8a6', '#ec4899', '#eab308'
	];

	const padding = { top: 10, right: 20, bottom: 30, left: 60 };
	const chartW = $derived(width - padding.left - padding.right);
	const chartH = $derived(height - padding.top - padding.bottom);

	const allValues = $derived(
		compareData.series.flatMap((s) => s.points.map((p) => p.y))
	);
	const yMin = $derived(Math.min(0, ...allValues));
	const yMax = $derived(Math.max(...allValues, 1));
	const yRange = $derived(yMax - yMin || 1);

	const allTimes = $derived(
		compareData.series.flatMap((s) => s.points.map((p) => new Date(p.x).getTime()))
	);
	const tMin = $derived(Math.min(...allTimes));
	const tMax = $derived(Math.max(...allTimes, tMin + 1));
	const tRange = $derived(tMax - tMin || 1);

	function xPos(ts: number): number {
		return padding.left + ((ts - tMin) / tRange) * chartW;
	}

	function yPos(val: number): number {
		return padding.top + chartH - ((val - yMin) / yRange) * chartH;
	}

	function buildPath(points: Array<{ x: string; y: number }>): string {
		if (points.length === 0) return '';
		if (points.length === 1) {
			const p = points[0];
			const y = yPos(p.y);
			return `M ${padding.left} ${y} L ${padding.left + chartW} ${y}`;
		}
		return points
			.map((p, i) => {
				const cmd = i === 0 ? 'M' : 'L';
				const ts = new Date(p.x).getTime();
				return `${cmd} ${xPos(ts).toFixed(1)} ${yPos(p.y).toFixed(1)}`;
			})
			.join(' ');
	}

	function yTicks(): number[] {
		const count = 4;
		const ticks: number[] = [];
		for (let i = 0; i <= count; i++) {
			ticks.push(yMin + (yRange / count) * i);
		}
		return ticks;
	}

	function formatAxisValue(v: number): string {
		return formatNumber(Math.round(v));
	}
</script>

<svg
	{width}
	{height}
	viewBox="0 0 {width} {height}"
	role="img"
	aria-label="Comparison chart"
	class="overflow-visible w-full h-auto"
>
	<!-- Y-axis grid lines -->
	{#each yTicks() as tick}
		{@const y = yPos(tick)}
		<line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="var(--border-color, #333)" stroke-width="1" opacity="0.3" />
		<text x={padding.left - 8} y={y + 4} text-anchor="end" fill="var(--muted-color, #888)" font-size="10">
			{formatAxisValue(tick)}
		</text>
	{/each}

	<!-- Lines -->
	{#each compareData.series as series, i}
		{@const color = COLORS[i % COLORS.length]}
		<path d={buildPath(series.points)} fill="none" stroke={color} stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
	{/each}

	<!-- Legend -->
	<g transform="translate({padding.left}, {height - 4})">
		{#each compareData.series as series, i}
			{@const x = i * 140}
			<rect x={x} y={-10} width={10} height={10} rx={2} fill={COLORS[i % COLORS.length]} />
			<text x={x + 14} y={0} fill="var(--muted-color, #888)" font-size="10">
				{series.title.length > 18 ? series.title.slice(0, 17) + '…' : series.title}
			</text>
		{/each}
	</g>
</svg>
