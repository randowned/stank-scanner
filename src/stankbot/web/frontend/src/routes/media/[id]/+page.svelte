<script lang="ts">
	import { base } from '$app/paths';
	import { untrack } from 'svelte';
	import { apiFetch } from '$lib/api';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem, MetricSnapshot } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import SelectDropdown from '$lib/components/SelectDropdown.svelte';
	import Chart from '$lib/components/Chart.svelte';
	import RelativeTime from '$lib/components/RelativeTime.svelte';

	let { data } = $props();

	const item = $derived(data.item as MediaItem | null);
	const initialHistory = $derived(data.history as MetricSnapshot[]);

	let selectedMetric = $state<string>('view_count');
	let selectedDays = $state<number>(30);
	let history = $state<MetricSnapshot[]>(untrack(() => initialHistory));
	let loadingHistory = $state(false);

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

	$effect(() => {
		void selectedMetric;
		void selectedDays;
		void loadHistory();
	});

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
						color: 'var(--muted-color, #888)',
						font: { size: 10 }
					},
					grid: { display: false }
				},
				y: {
					title: { display: true, text: metricLabel(selectedMetric), color: 'var(--muted-color, #888)' },
					ticks: {
						callback: (value: number) => {
							if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + 'M';
							if (value >= 1_000) return (value / 1_000).toFixed(1) + 'K';
							return value.toString();
						},
						color: 'var(--muted-color, #888)',
						font: { size: 10 }
					},
					grid: { color: 'var(--border-color, #333)', drawBorder: false }
				}
			},
			plugins: {
				legend: { display: false }
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
			</div>
		</div>

		<div class="text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}" data-testid="media-freshness">
			{freshness.label}
		</div>
	</div>
{/if}
