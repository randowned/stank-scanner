<script lang="ts">
	interface Props {
		values: number[];
		width?: number;
		height?: number;
		stroke?: string;
		fill?: string;
		ariaLabel?: string;
	}

	let {
		values,
		width = 160,
		height = 40,
		stroke = 'currentColor',
		fill = 'none',
		ariaLabel = 'Sparkline'
	}: Props = $props();

	const path = $derived(buildPath(values, width, height));
	const area = $derived(buildArea(values, width, height));

	function buildPath(vs: number[], w: number, h: number): string {
		if (vs.length === 0) return '';
		if (vs.length === 1) {
			const y = h / 2;
			return `M 0 ${y} L ${w} ${y}`;
		}
		const min = Math.min(...vs);
		const max = Math.max(...vs);
		const range = max - min || 1;
		const stepX = w / (vs.length - 1);
		const pts = vs.map((v, i) => {
			const x = i * stepX;
			const y = h - ((v - min) / range) * h;
			return `${x.toFixed(2)},${y.toFixed(2)}`;
		});
		return 'M ' + pts.join(' L ');
	}

	function buildArea(vs: number[], w: number, h: number): string {
		if (vs.length < 2) return '';
		const line = buildPath(vs, w, h).slice(2);
		return `M 0 ${h} L ${line} L ${w} ${h} Z`;
	}
</script>

<svg
	{width}
	{height}
	viewBox="0 0 {width} {height}"
	role="img"
	aria-label={ariaLabel}
	class="overflow-visible"
>
	{#if fill !== 'none' && area}
		<path d={area} fill={fill} />
	{/if}
	{#if path}
		<path d={path} fill="none" stroke={stroke} stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />
	{/if}
</svg>
