<script lang="ts">
	import { base } from '$app/paths';
	import { untrack } from 'svelte';
	import { apiFetch } from '$lib/api';
	import { formatNumber, formatRelativeTime, formatFreshness } from '$lib/format';
	import type { MediaItem, MetricSnapshot, CompareData } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import Select from '$lib/components/Select.svelte';
	import Button from '$lib/components/Button.svelte';
	import Sparkline from '$lib/components/Sparkline.svelte';
	import ComparisonChart from '$lib/components/ComparisonChart.svelte';

	let { data } = $props();

	const item = $derived(data.item as MediaItem | null);
	const initialHistory = $derived(data.history as MetricSnapshot[]);

	let selectedMetric = $state<string>('view_count');
	let selectedDays = $state<number>(30);
	let history = $state<MetricSnapshot[]>(untrack(() => initialHistory));
	let loadingHistory = $state(false);

	let compareIds = $state<string>('');
	let compareData = $state<CompareData | null>(null);
	let loadingCompare = $state(false);

	const metricOptions = [
		{ value: 'view_count', label: 'Views' },
		{ value: 'like_count', label: 'Likes' },
		{ value: 'comment_count', label: 'Comments' }
	];

	const daysOptions = [
		{ value: 7, label: '7 days' },
		{ value: 30, label: '30 days' },
		{ value: 90, label: '90 days' },
		{ value: 365, label: '1 year' }
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

	async function loadComparison() {
		if (!item || !compareIds.trim()) return;
		const ids = [item.id, ...compareIds.split(',').map((s) => Number(s.trim())).filter((n) => !isNaN(n))];
		if (ids.length < 2) return;
		loadingCompare = true;
		try {
			const res = await apiFetch<CompareData>(
				`/api/media/compare?ids=${ids.join(',')}&metric=${selectedMetric}&days=${selectedDays}`
			);
			compareData = res;
		} catch {
			compareData = null;
		} finally {
			loadingCompare = false;
		}
	}

	const sparkValues = $derived(history.map((h) => h.value));

	const freshness = $derived(formatFreshness(item?.metrics_last_fetched_at, 10));
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
				{#if item.thumbnail_url}
					<img src={item.thumbnail_url} alt={item.title} class="w-full rounded-lg" loading="lazy" />
				{:else}
					<div class="w-full aspect-video bg-border rounded-lg flex items-center justify-center text-muted text-5xl">
						▶️
					</div>
				{/if}
				<div class="mt-3 text-sm space-y-1">
					<div class="text-muted">
						Published: <span class="text-text">{item.published_at ? formatRelativeTime(item.published_at) : '—'}</span>
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

				<div class="flex items-center gap-2 mb-3 flex-wrap">
					<Select options={metricOptions} bind:value={selectedMetric} testId="media-detail-metric" />
					<Select options={daysOptions} bind:value={selectedDays} testId="media-detail-days" />
					<Button variant="secondary" onclick={loadHistory} loading={loadingHistory} testId="media-detail-refresh-history">
						Reload
					</Button>
				</div>

				<div class="panel mb-4">
					<h3 class="text-sm font-semibold mb-2">{metricLabel(selectedMetric)} over time</h3>
					{#if history.length > 0}
						<Sparkline values={sparkValues} width={600} height={160} stroke="var(--accent-color)" fill="var(--accent-color-10)" ariaLabel={metricLabel(selectedMetric)} />
					{:else}
						<div class="text-muted text-sm py-4 text-center">No history data yet</div>
					{/if}
				</div>

				<div class="panel">
					<h3 class="text-sm font-semibold mb-2">Compare with other videos</h3>
					<div class="flex items-center gap-2 flex-wrap">
						<input
							type="text"
							class="input flex-1 min-w-0"
							placeholder="Comma-separated media IDs (e.g. 2,3)"
							bind:value={compareIds}
							data-testid="media-compare-input"
						/>
						<Button variant="secondary" onclick={loadComparison} loading={loadingCompare} testId="media-compare-load">
							Compare
						</Button>
					</div>
					{#if compareData}
						<div class="mt-3">
							<ComparisonChart {compareData} />
						</div>
					{/if}
				</div>
			</div>
		</div>

		<div class="text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}" data-testid="media-freshness">
			{freshness.label}
		</div>
	</div>
{/if}
