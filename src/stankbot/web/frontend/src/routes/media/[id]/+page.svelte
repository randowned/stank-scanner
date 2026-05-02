<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { untrack } from 'svelte';
	import { apiFetch } from '$lib/api';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem, MetricSnapshot, CompareData, MetricDef, ProviderDef } from '$lib/types';
	import { providersByType, loadProviders } from '$lib/stores';
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
	const providers = $derived((data.providers as ProviderDef[]) ?? []);

	$effect(() => {
		if (providers.length > 0) {
			const map: Record<string, ProviderDef> = {};
			for (const p of providers) map[p.type] = p;
			providersByType.set(map);
		}
	});

	void loadProviders();

	const provider = $derived(item ? $providersByType[item.media_type] : undefined);
	const providerMetrics = $derived<MetricDef[]>(provider?.metrics ?? []);

	const initialMetric = $derived(item?.media_type === 'spotify' ? 'popularity' : 'view_count');
	let selectedMetric = $state<string>('view_count');
	$effect(() => {
		// align selected metric with provider once known
		if (providerMetrics.length > 0 && !providerMetrics.some((m) => m.key === selectedMetric)) {
			selectedMetric = providerMetrics[0].key;
		}
	});
	$effect(() => {
		// initial metric on first load
		if (item) untrack(() => { selectedMetric = initialMetric; });
	});

	// Range value: number of hours; days option encoded as hours = days*24
	let selectedHours = $state<number>(24);
	let history = $state<MetricSnapshot[]>(untrack(() => initialHistory));
	let loadingHistory = $state(false);

	let compareIds = $state<string[]>([]);
	let compareData = $state<CompareData | null>(null);
	let loadingCompare = $state(false);

	const metricOptions = $derived(
		providerMetrics.length > 0
			? providerMetrics.map((m) => ({ value: m.key, label: m.label, icon: m.icon || '📊' }))
			: [
				{ value: 'view_count', label: 'Views', icon: '👁️' },
				{ value: 'like_count', label: 'Likes', icon: '👍' },
				{ value: 'comment_count', label: 'Comments', icon: '💬' }
			]
	);

	const rangeOptions = [
		{ value: 6, label: '6 hours', icon: '⏱️' },
		{ value: 12, label: '12 hours', icon: '⏱️' },
		{ value: 24, label: '1 day', icon: '📅' },
		{ value: 24 * 7, label: '7 days', icon: '📅' },
		{ value: 24 * 30, label: '30 days', icon: '📅' },
		{ value: 24 * 90, label: '90 days', icon: '📅' },
		{ value: 24 * 365, label: '1 year', icon: '📅' }
	];

	const hasCompare = $derived(compareIds.length > 0);

	$effect(() => {
		const raw = $page.url.searchParams.get('compare');
		if (raw) {
			compareIds = raw.split(',').map((s) => s.trim()).filter(Boolean);
		}
	});

	function activeMetric(): MetricDef | undefined {
		return providerMetrics.find((m) => m.key === selectedMetric);
	}

	function metricFormat(): string {
		return activeMetric()?.format ?? 'number';
	}

	function metricLabel(key: string): string {
		const m = providerMetrics.find((mm) => mm.key === key);
		if (m) return m.label;
		const fallback = metricOptions.find((o) => o.value === key);
		return fallback?.label ?? key;
	}

	function formatMetricValue(key: string, value: number): string {
		const m = providerMetrics.find((mm) => mm.key === key);
		if (m?.format === 'percentage') return `${Math.round(value)}%`;
		if (m?.format === 'duration') {
			const mins = Math.floor(value / 60);
			const secs = Math.floor(value % 60);
			return `${mins}:${String(secs).padStart(2, '0')}`;
		}
		return formatNumber(value);
	}

	function metricValue(key: string): number {
		return item?.metrics?.[key]?.value ?? 0;
	}

	function buildHistoryUrl(): string {
		if (!item) return '';
		if (selectedHours < 24) {
			return `/api/media/${item.id}/history?metric=${selectedMetric}&hours=${selectedHours}`;
		}
		const days = Math.max(1, Math.round(selectedHours / 24));
		return `/api/media/${item.id}/history?metric=${selectedMetric}&days=${days}`;
	}

	async function loadHistory() {
		if (!item) return;
		loadingHistory = true;
		try {
			const res = await apiFetch<{ history: MetricSnapshot[] }>(buildHistoryUrl());
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
			const days = Math.max(1, Math.round(selectedHours / 24));
			const res = await apiFetch<CompareData>(
				`/api/media/compare?ids=${compareIds.join(',')}&metric=${selectedMetric}&days=${days}&align=calendar`
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
		void selectedHours;
		void loadHistory();
		if (hasCompare) void loadComparison();
	});

	function clearComparison() {
		compareIds = [];
		compareData = null;
		void goto(`${base}/media/${item?.id ?? ''}`);
	}

	function buildChartDatasets() {
		return [{
			label: metricLabel(selectedMetric),
			data: history.map((h) => ({
				x: new Date(h.fetched_at).getTime(),
				y: h.value
			}))
		}];
	}

	function timeDisplayFormats() {
		return {
			millisecond: 'HH:mm:ss',
			second: 'HH:mm:ss',
			minute: 'HH:mm',
			hour: 'HH:mm',
			day: 'MMM d',
			week: 'MMM d',
			month: 'MMM yyyy',
			quarter: 'MMM yyyy',
			year: 'yyyy'
		};
	}

	function yTickCallback(value: number): string {
		const fmt = metricFormat();
		if (fmt === 'percentage') return `${Math.round(value)}%`;
		if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + 'M';
		if (value >= 1_000) return (value / 1_000).toFixed(1) + 'K';
		return value.toString();
	}

	function buildChartOptions(): Record<string, unknown> {
		const isPercentage = metricFormat() === 'percentage';
		return {
			scales: {
				x: {
					type: 'time',
					time: {
						tooltipFormat: 'MMM d, yyyy HH:mm',
						displayFormats: timeDisplayFormats()
					},
					ticks: {
						maxTicksLimit: 8,
						color: '#9aa4b2',
						font: { size: 10 },
						source: 'auto'
					},
					grid: { display: false }
				},
				y: {
					title: { display: true, text: metricLabel(selectedMetric), color: '#9aa4b2' },
					...(isPercentage ? { min: 0, max: 100 } : { beginAtZero: false }),
					ticks: {
						callback: yTickCallback,
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
					type: 'time',
					time: {
						tooltipFormat: 'MMM d, yyyy HH:mm',
						displayFormats: timeDisplayFormats()
					},
					ticks: { maxTicksLimit: 8, color: '#9aa4b2', font: { size: 10 } },
					grid: { display: false }
				},
				y: {
					title: { display: true, text: cd.metric?.label ?? '', color: '#9aa4b2' },
					ticks: { color: '#9aa4b2', font: { size: 10 } },
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
						boxHeight: 10
					}
				}
			}
		};
	}

	const freshness = $derived(formatFreshness(item?.metrics_last_fetched_at, 10));
	const graphs = $derived(history.length > 0);

	function externalUrl(): string | null {
		if (!item) return null;
		if (item.media_type === 'youtube') return `https://youtu.be/${item.external_id}`;
		if (item.media_type === 'spotify') return `https://open.spotify.com/track/${item.external_id}`;
		return null;
	}

	const sparseHint = $derived(history.length > 0 && history.length < 2);
</script>

{#if !item}
	<ErrorState title="Not found" message="This media item could not be found." />
{:else}
	<div class="p-4 space-y-4">
		<div class="flex items-center justify-between">
			<a href="{base}/media" class="text-sm text-muted hover:text-accent transition-colors">← Back to Media</a>
			<div class="flex items-center gap-2">
				<span
					class="text-xs px-2 py-1 rounded-full border {freshness.state === 'fresh' ? 'border-green-700 text-green-400' : freshness.state === 'stale' ? 'border-amber-700 text-amber-400' : 'border-red-700 text-red-400'}"
					data-testid="media-freshness-pill"
					title={freshness.label}
				>
					● {freshness.label}
				</span>
				{#if externalUrl()}
					<a
						href={externalUrl()}
						target="_blank"
						rel="noopener noreferrer"
						class="text-xs px-3 py-1 rounded border border-border hover:border-accent text-text no-underline"
						data-testid="media-external-link"
					>
						Open on {provider?.label ?? item.media_type} ↗
					</a>
				{/if}
			</div>
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
						Type: <span class="text-text capitalize">{provider?.label ?? item.media_type}</span>
					</div>
				</div>
			</div>

			<div class="md:col-span-2">
				<div
					class="grid gap-3 mb-4"
					style="grid-template-columns: repeat({Math.max(1, metricOptions.length)}, minmax(0, 1fr));"
				>
					{#each metricOptions as opt (opt.value)}
						<StatTile
							value={formatMetricValue(opt.value, metricValue(opt.value))}
							label={opt.label}
							testId="media-detail-{opt.value}"
							valueTestId="media-detail-{opt.value}-value"
						/>
					{/each}
				</div>

				<div class="flex items-center gap-2 mb-3 flex-nowrap">
					<SelectDropdown options={metricOptions} bind:value={selectedMetric} testId="media-detail-metric" />
					<SelectDropdown options={rangeOptions} bind:value={selectedHours} testId="media-detail-range" />
					{#if hasCompare}
						<Button variant="ghost" onclick={clearComparison} size="sm" testId="media-clear-compare">Clear comparison</Button>
					{/if}
				</div>

				<div class="panel mb-4">
					<h3 class="text-sm font-semibold mb-2">{metricLabel(selectedMetric)} over time</h3>
					{#if graphs}
						<div class={loadingHistory ? 'opacity-60 transition-opacity' : ''} data-testid="media-detail-chart">
							<Chart datasets={buildChartDatasets()} options={buildChartOptions()} height={220} />
						</div>
						{#if sparseHint}
							<div class="text-xs text-muted mt-2">
								Only 1 data point yet — refresh again or wait for the next scheduled poll.
							</div>
						{/if}
					{:else}
						<div class="text-muted text-sm py-4 text-center" data-testid="media-detail-no-history">No history data yet — waiting for the next scheduled poll.</div>
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
	</div>
{/if}
