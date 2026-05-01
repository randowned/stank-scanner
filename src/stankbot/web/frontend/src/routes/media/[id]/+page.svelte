<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { untrack } from 'svelte';
	import { apiFetch } from '$lib/api';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem, MetricSnapshot, CompareData } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import SelectDropdown from '$lib/components/SelectDropdown.svelte';
	import Button from '$lib/components/Button.svelte';
	import Chart from '$lib/components/Chart.svelte';
	import RelativeTime from '$lib/components/RelativeTime.svelte';

	let { data } = $props();

	const item = $derived(data.item as MediaItem | null);
	const initialHistory = $derived(data.history as MetricSnapshot[]);

	let selectedMetric = $state<string>('view_count');
	let selectedDays = $state<number>(7);
	let history = $state<MetricSnapshot[]>(untrack(() => initialHistory));
	let loadingHistory = $state(false);

	let compareIds = $state<string[]>([]);
	let compareData = $state<CompareData | null>(null);
	let loadingCompare = $state(false);

	const metricOptions = [
		{ value: 'view_count', label: 'Views', icon: '👁️' },
		{ value: 'like_count', label: 'Likes', icon: '👍' },
		{ value: 'comment_count', label: 'Comments', icon: '💬' }
	];

	const daysOptions = [
		{ value: 7, label: '7 days', icon: '📅' },
		{ value: 30, label: '30 days', icon: '📅' },
		{ value: 90, label: '90 days', icon: '📅' },
		{ value: 365, label: '1 year', icon: '📅' }
	];

	const hasCompare = $derived(compareIds.length > 0);

	// Read compare IDs from query params on init
	$effect(() => {
		const raw = $page.url.searchParams.get('compare');
		if (raw) {
			compareIds = raw.split(',').map(s => s.trim()).filter(Boolean);
		}
	});

	function metricValue(key: string): number {
		return item?.metrics?.[key]?.value ?? 0;
	}

	function metricLabel(key: string): string {
		const opt = metricOptions.find((o) => o.value === key);
		return opt?.label ?? key;
	}

	async function loadHistory() {
		if (!item) return;
		loadingHistory = true;
		try {
			const res = await apiFetch<{ history: MetricSnapshot[] }>(
				`/api/media/${item.id}/history?metric=${selectedMetric}&days=${selectedDays}`
			);
			history = res.history;
		} catch {
			history = [];
		} finally {
			loadingHistory = false;
		}
	}

	async function loadComparison() {
		if (!item || compareIds.length === 0) return;
		loadingCompare = true;
		try {
			const res = await apiFetch<CompareData>(
				`/api/media/compare?ids=${compareIds.join(',')}&metric=${selectedMetric}&days=${selectedDays}&align=calendar`
			);
			compareData = res;
		} catch {
			compareData = null;
		} finally {
			loadingCompare = false;
		}
	}

	$effect(() => {
		void selectedMetric;
		void selectedDays;
		void loadHistory();
		if (hasCompare) void loadComparison();
	});

	function clearComparison() {
		compareIds = [];
		compareData = null;
		void goto(`${base}/media/${item?.id ?? ''}`);
	}

	function buildChartDatasets(): Array<{ label: string; data: Array<{ x: number; y: number }> }> {
		return [{
			label: metricLabel(selectedMetric),
			data: history.map((h) => ({
				x: new Date(h.fetched_at).getTime(),
				y: h.value
			}))
		}];
	}

	function buildChartOptions(): Record<string, unknown> {
		return {
			scales: {
				x: {
					ticks: {
						callback: (value: number) => {
							const d = new Date(value);
							return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
						},
						maxTicksLimit: 7,
						color: '#9aa4b2',
						font: { size: 10 }
					},
					grid: { display: false }
				},
				y: {
					title: { display: true, text: metricLabel(selectedMetric), color: '#9aa4b2' },
					ticks: {
						callback: (value: number) => {
							if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + 'M';
							if (value >= 1_000) return (value / 1_000).toFixed(1) + 'K';
							return value.toString();
						},
						color: '#9aa4b2',
						font: { size: 10 }
					},
					grid: { color: '#262a33', drawBorder: false }
				}
			},
			plugins: {
				legend: { display: false }
			}
		};
	}

	function buildCompareDatasets(cd: CompareData) {
		if (!cd) return [];
		return cd.series.map((s) => ({
			label: s.title,
			data: s.points.map((p) => ({
				x: new Date(String(p.x)).getTime(),
				y: p.y
			}))
		}));
	}

	function buildCompareOptions(cd: CompareData): Record<string, unknown> {
		return {
			scales: {
				x: {
					ticks: {
						maxTicksLimit: 7,
						color: '#9aa4b2',
						font: { size: 10 }
					},
					grid: { display: false }
				},
				y: {
					title: { display: true, text: cd.metric?.label ?? '', color: '#9aa4b2' },
					ticks: {
						color: '#9aa4b2',
						font: { size: 10 }
					},
					grid: { color: '#262a33', drawBorder: false }
				}
			},
			plugins: {
				legend: {
					display: true,
					position: 'bottom',
					labels: {
						color: '#9aa4b2',
						font: { size: 11 },
						padding: 12,
						boxWidth: 10,
						boxHeight: 10,
					}
				}
			}
		};
	}

	const freshness = $derived(formatFreshness(item?.metrics_last_fetched_at, 10));

	const graphs = $derived(history.length > 0);
</script>

{#if !item}
	<ErrorState title="Not found" message="This media item could not be found." />
{:else}
	<div class="p-4 space-y-4">
		<div>
			<a href="{base}/media" class="text-sm text-muted hover:text-accent transition-colors">← Back to Media</a>
		</div>

		<PageHeader title={item.title} subtitle={item.channel_name ?? 'Unknown channel'} />

		<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-2">
			<div class="md:col-span-1">
				<div class="panel overflow-hidden p-0">
					{#if item.thumbnail_url}
						<img src={item.thumbnail_url} alt={item.title} class="w-full" loading="lazy" />
					{:else}
						<div class="w-full aspect-video bg-border flex items-center justify-center text-muted text-5xl">
							▶️
						</div>
					{/if}
				</div>
				<div class="mt-3 text-sm space-y-1">
					<div class="text-muted">
						Published: <RelativeTime datetime={item.published_at} class="text-text" />
					</div>
					{#if item.duration_seconds !== null && item.duration_seconds !== undefined}
						{@const mins = Math.floor((item.duration_seconds ?? 0) / 60)}
						{@const secs = (item.duration_seconds ?? 0) % 60}
						<div class="text-muted">
							Duration: <span class="text-text">{mins}:{String(secs).padStart(2, '0')}</span>
						</div>
					{/if}
					<div class="text-muted">
						Type: <span class="text-text capitalize">{item.media_type}</span>
					</div>
				</div>
			</div>

			<div class="md:col-span-2">
				<div class="grid grid-cols-3 gap-3 mb-4">
					<StatTile
						value={formatNumber(metricValue('view_count'))}
						label="Views"
						testId="media-detail-views"
						valueTestId="media-detail-views-value"
					/>
					<StatTile
						value={formatNumber(metricValue('like_count'))}
						label="Likes"
						testId="media-detail-likes"
						valueTestId="media-detail-likes-value"
					/>
					<StatTile
						value={formatNumber(metricValue('comment_count'))}
						label="Comments"
						testId="media-detail-comments"
						valueTestId="media-detail-comments-value"
					/>
				</div>

				<div class="flex items-center gap-2 mb-3 flex-nowrap">
					<SelectDropdown options={metricOptions} bind:value={selectedMetric} testId="media-detail-metric" />
					<SelectDropdown options={daysOptions} bind:value={selectedDays} testId="media-detail-days" />
					{#if hasCompare}
						<Button variant="ghost" onclick={clearComparison} size="sm" testId="media-clear-compare">Clear comparison</Button>
					{/if}
				</div>

				<div class="panel mb-4">
					<h3 class="text-sm font-semibold mb-2">{metricLabel(selectedMetric)} over time</h3>
					{#if graphs}
						<div class={loadingHistory ? 'opacity-60 transition-opacity' : ''}>
							<Chart datasets={buildChartDatasets()} options={buildChartOptions()} height={220} />
						</div>
					{:else}
						<div class="text-muted text-sm py-4 text-center">No history data yet</div>
					{/if}
				</div>

				{#if hasCompare && compareData}
					<div class="panel mb-4">
						<h3 class="text-sm font-semibold mb-2">
							{metricLabel(selectedMetric)} — comparison with {compareData.series.length} other media
						</h3>
						<div class={loadingCompare ? 'opacity-60 transition-opacity' : ''}>
							<Chart datasets={buildCompareDatasets(compareData)} options={buildCompareOptions(compareData)} height={220} />
						</div>
					</div>
				{:else if hasCompare && !compareData && !loadingCompare}
					<div class="panel mb-4">
						<div class="text-muted text-sm py-4 text-center">No comparison data available</div>
					</div>
				{/if}
			</div>
		</div>

		<div class="text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}" data-testid="media-freshness">
			{freshness.label}
		</div>
	</div>
{/if}
