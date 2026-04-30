<script lang="ts">
	import { base } from '$app/paths';
	import { apiFetch } from '$lib/api';
	import { formatNumber, formatRelativeTime, formatFreshness } from '$lib/format';
	import type { MediaItem, CompareData } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Select from '$lib/components/Select.svelte';
	import Button from '$lib/components/Button.svelte';
	import ComparisonChart from '$lib/components/ComparisonChart.svelte';

	let { data } = $props();

	const items = $derived(data.items as MediaItem[]);

	let timeframe = $state<number>(30);
	let selectedMetric = $state<string>('view_count');
	let compareMode = $state(false);
	let selectedIds = $state<number[]>([]);
	let compareData = $state<CompareData | null>(null);
	let loadingCompare = $state(false);

	const timeframeOptions = [
		{ value: 7, label: 'Last 7 days' },
		{ value: 30, label: 'Last 30 days' },
		{ value: 90, label: 'Last 90 days' },
		{ value: 365, label: 'Last year' }
	];

	const metricOptions = [
		{ value: 'view_count', label: 'Views' },
		{ value: 'like_count', label: 'Likes' },
		{ value: 'comment_count', label: 'Comments' }
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
			const res = await apiFetch<CompareData>(
				`/api/media/compare?ids=${selectedIds.join(',')}&metric=${selectedMetric}&days=${timeframe}`
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
</script>

<PageHeader title="Media" subtitle="Media analytics" />

<div class="p-4 space-y-4">
	<div class="flex flex-wrap items-center gap-3">
		<div class="flex items-center gap-2">
			<Select options={timeframeOptions} bind:value={timeframe} testId="media-timeframe" />
		</div>
		<div class="flex items-center gap-2">
			<Select options={metricOptions} bind:value={selectedMetric} testId="media-metric" />
		</div>
		<Button
			variant={compareMode ? 'primary' : 'secondary'}
			onclick={() => {
				compareMode = !compareMode;
				if (!compareMode) clearSelection();
			}}
			testId="media-compare-toggle"
		>
			{compareMode ? 'Cancel compare' : 'Compare'}
		</Button>
		{#if compareMode && selectedIds.length >= 2}
			<Button variant="secondary" onclick={loadComparison} loading={loadingCompare} testId="media-compare-go">
				Compare {selectedIds.length} selected
			</Button>
			<Button variant="ghost" onclick={clearSelection}>Clear</Button>
		{/if}
	</div>

	{#if compareData}
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">{metricLabel(selectedMetric)} comparison — last {timeframe} days</h2>
			<ComparisonChart {compareData} />
		</div>
	{/if}

	{#if items.length === 0}
		<EmptyState icon="📊" title="No media yet" message="Admins can add YouTube and Spotify media from the admin panel." />
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each items as item (item.id)}
				{@const freshness = formatFreshness(item.metrics_last_fetched_at, 10)}
				<a
					href={getVideoUrl(item.id)}
					class="panel block hover:border-accent transition-colors relative {compareMode ? (selectedIds.includes(item.id) ? 'ring-2 ring-accent' : 'opacity-50') : ''}"
					data-testid="media-card"
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
					{#if item.thumbnail_url}
						<img src={item.thumbnail_url} alt={item.title} class="w-full h-40 object-cover rounded-t-md" loading="lazy" />
					{:else}
						<div class="w-full h-40 bg-border rounded-t-md flex items-center justify-center text-muted text-4xl">
							▶️
						</div>
					{/if}
					<div class="p-3">
						<h3 class="font-semibold text-text line-clamp-2 text-sm mb-1">{item.title}</h3>
						<p class="text-xs text-muted mb-2">{item.channel_name ?? 'Unknown'}</p>
						<div class="flex items-center justify-between text-xs">
							<span class="text-muted" data-testid="media-published">{item.published_at ? formatRelativeTime(item.published_at) : '—'}</span>
							<span class="font-mono text-text" data-testid="media-metric-value">
								{formatNumber(metricValue(item, selectedMetric))}
							</span>
						</div>
						<div class="mt-1 text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}" data-testid="media-freshness">
							{freshness.label}
						</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
