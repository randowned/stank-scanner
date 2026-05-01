<script lang="ts">
	import { base } from '$app/paths';
	import { apiFetch } from '$lib/api';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem, CompareData } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SelectDropdown from '$lib/components/SelectDropdown.svelte';
	import Button from '$lib/components/Button.svelte';
	import Chart from '$lib/components/Chart.svelte';
	import RelativeTime from '$lib/components/RelativeTime.svelte';

	let { data } = $props();

	const items = $derived(data.items as MediaItem[]);

	let timeframe = $state<number>(30);
	let selectedMetric = $state<string>('view_count');
	let compareMode = $state(false);
	let selectedIds = $state<number[]>([]);
	let compareData = $state<CompareData | null>(null);
	let loadingCompare = $state(false);
	let alignRelease = $state(false);

	const timeframeOptions = [
		{ value: 7, label: '7 days', icon: '📅' },
		{ value: 30, label: '30 days', icon: '📅' },
		{ value: 90, label: '90 days', icon: '📅' },
		{ value: 365, label: '1 year', icon: '📅' }
	];

	const metricOptions = [
		{ value: 'view_count', label: 'Views', icon: '👁️' },
		{ value: 'like_count', label: 'Likes', icon: '👍' },
		{ value: 'comment_count', label: 'Comments', icon: '💬' }
	];

	function metricValue(item: MediaItem, key: string): number {
		return item.metrics?.[key]?.value ?? 0;
	}

	function metricLabel(key: string): string {
		const opt = metricOptions.find((o) => o.value === key);
		return opt?.label ?? key;
	}

	function toggleSelect(id: number) {
		if (selectedIds.includes(id)) {
			selectedIds = selectedIds.filter((sid) => sid !== id);
		} else {
			selectedIds = [...selectedIds, id];
		}
	}

	async function loadComparison() {
		if (selectedIds.length < 2) return;
		loadingCompare = true;
		try {
			const align = alignRelease ? 'release' : 'calendar';
			const res = await apiFetch<CompareData>(
				`/api/media/compare?ids=${selectedIds.join(',')}&metric=${selectedMetric}&days=${timeframe}&align=${align}`
			);
			compareData = res;
		} catch {
			compareData = null;
		} finally {
			loadingCompare = false;
		}
	}

	function clearSelection() {
		selectedIds = [];
		compareData = null;
	}

	function getVideoUrl(id: number): string {
		return `${base}/media/${id}`;
	}

	function buildChartDatasets(cd: CompareData) {
		if (!cd) return [];
		return cd.series.map((s) => ({
			label: s.title,
			data: s.points.map((p) => ({
				x: cd.aligned ? Number(p.x) : new Date(String(p.x)).getTime(),
				y: p.y
			}))
		}));
	}

	function buildChartOptions(cd: CompareData) {
		const opts: Record<string, unknown> = {};
		if (cd.aligned) {
			opts.scales = {
				x: {
					title: { display: true, text: 'Days since release', color: 'var(--muted-color, #888)' },
					ticks: {
						callback: (value: number) => (value % 7 === 0 ? `Day ${value}` : ''),
						color: 'var(--muted-color, #888)',
						font: { size: 10 }
					},
					grid: { display: false }
				},
				y: {
					title: { display: true, text: cd.metric?.label ?? '', color: 'var(--muted-color, #888)' },
				}
			};
		} else {
			opts.scales = {
				x: {
					ticks: {
						callback: (value: number) => {
							const d = new Date(value);
							return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
						},
						maxTicksLimit: 7,
						color: 'var(--muted-color, #888)',
						font: { size: 10 }
					},
					grid: { display: false }
				},
				y: {
					title: { display: true, text: cd.metric?.label ?? '', color: 'var(--muted-color, #888)' },
				}
			};
		}
		return opts;
	}

	const showCompareBtn = $derived(items.length > 1);
</script>

<div class="p-4 space-y-4">
	<PageHeader title="Media" subtitle="Media analytics" />

	<div class="flex flex-wrap items-center gap-2">
		<SelectDropdown options={timeframeOptions} bind:value={timeframe} testId="media-timeframe" />
		<SelectDropdown options={metricOptions} bind:value={selectedMetric} testId="media-metric" />
		{#if showCompareBtn}
			<Button
				variant={compareMode ? 'primary' : 'secondary'}
				onclick={() => {
					compareMode = !compareMode;
					if (!compareMode) clearSelection();
				}}
				testId="media-compare-toggle"
				size="sm"
			>
				{compareMode ? 'Cancel' : 'Compare'}
			</Button>
		{/if}
		{#if compareMode && selectedIds.length >= 2}
			<Button variant="secondary" onclick={loadComparison} loading={loadingCompare} testId="media-compare-go" size="sm">
				Compare {selectedIds.length}
			</Button>
			<Button variant="ghost" onclick={clearSelection} size="sm">Clear</Button>
			<Button
				variant="ghost"
				onclick={() => { alignRelease = !alignRelease; if (compareData) loadComparison(); }}
				title={alignRelease ? 'Switch to calendar view' : 'Align by release date'}
				size="sm"
			>
				{alignRelease ? '🚀 Since release' : '📅 Calendar'}
			</Button>
		{/if}
	</div>

	{#if compareData}
		<div class="panel">
			<h2 class="text-sm font-semibold mb-3">
				{metricLabel(selectedMetric)} — {compareData.aligned ? 'first' : 'past'} {timeframe} days
			</h2>
			<Chart datasets={buildChartDatasets(compareData)} options={buildChartOptions(compareData)} height={250} />
		</div>
	{/if}

	{#if items.length === 0}
		<EmptyState icon="📊" title="No media yet" message="Admins can add YouTube and Spotify media from the admin panel." />
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each items as item (item.id)}
				{@const freshness = formatFreshness(item.metrics_last_fetched_at, 10)}
				<div
					class="panel overflow-hidden p-0 block hover:border-accent transition-colors relative {compareMode ? (selectedIds.includes(item.id) ? 'ring-2 ring-accent' : 'opacity-50') : ''}"
				>
					{#if compareMode}
						<button
							type="button"
							class="absolute top-2 right-2 z-10 w-6 h-6 rounded border-2 flex items-center justify-center {selectedIds.includes(item.id) ? 'bg-accent border-accent text-white' : 'border-muted bg-panel'}"
							onclick={(e) => { e.preventDefault(); toggleSelect(item.id); }}
							data-testid="media-select-check"
						>
							{#if selectedIds.includes(item.id)}✓{/if}
						</button>
					{/if}
					<a href={getVideoUrl(item.id)} class="block no-underline" data-testid="media-card">
						{#if item.thumbnail_url}
							<img src={item.thumbnail_url} alt={item.title} class="w-full h-40 object-cover" loading="lazy" />
						{:else}
							<div class="w-full h-40 bg-border flex items-center justify-center text-muted text-4xl">
								▶️
							</div>
						{/if}
						<div class="p-3">
							<h3 class="font-semibold text-text line-clamp-2 text-sm mb-1">{item.title}</h3>
							<p class="text-xs text-muted mb-2">{item.channel_name ?? 'Unknown'}</p>
							<div class="flex items-center justify-between text-xs">
								<RelativeTime datetime={item.published_at} short testId="media-published" />
								<span class="font-mono text-text" data-testid="media-metric-value">
									{formatNumber(metricValue(item, selectedMetric))}
								</span>
							</div>
							<div class="mt-1 text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}" data-testid="media-freshness">
								{freshness.label}
							</div>
						</div>
					</a>
				</div>
			{/each}
		</div>
	{/if}
</div>
