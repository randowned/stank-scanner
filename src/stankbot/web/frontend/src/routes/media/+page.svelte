<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Tabs from '$lib/components/Tabs.svelte';
	import Button from '$lib/components/Button.svelte';
	import RelativeTime from '$lib/components/RelativeTime.svelte';

	let { data } = $props();

	const items = $derived(data.items as MediaItem[]);

	let activeType = $state<string>('');
	let compareMode = $state(false);
	let selectedIds = $state<number[]>([]);

	const typeTabs = [
		{ value: '', label: 'All' },
		{ value: 'youtube', label: 'YouTube' },
		{ value: 'spotify', label: 'Spotify' },
	];

	const filteredItems = $derived(
		activeType ? items.filter((i) => i.media_type === activeType) : items
	);

	function borderClass(type: string): string {
		if (type === 'youtube') return 'border-l-[3px] border-l-[#ff0000]/70';
		if (type === 'spotify') return 'border-l-[3px] border-l-[#1db954]/70';
		return '';
	}

	function metricValue(item: MediaItem, key: string): number {
		return item.metrics?.[key]?.value ?? 0;
	}

	function toggleSelect(id: number) {
		if (selectedIds.includes(id)) {
			selectedIds = selectedIds.filter((sid) => sid !== id);
		} else {
			selectedIds = [...selectedIds, id];
		}
	}

	function clearSelection() {
		selectedIds = [];
	}

	function compareSelected() {
		if (selectedIds.length < 2) return;
		const primary = selectedIds[0];
		const extras = selectedIds.slice(1);
		void goto(`${base}/media/${primary}?compare=${extras.join(',')}&metric=view_count&days=7`);
	}

	const showCompareBtn = $derived(filteredItems.length > 1);
</script>

<div class="p-4 space-y-4">
	<PageHeader title="Media" subtitle="Media analytics" />

	<Tabs tabs={typeTabs} bind:value={activeType} />

	<div class="flex flex-wrap items-center gap-2">
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
			<Button variant="primary" onclick={compareSelected} testId="media-compare-go" size="sm">
				Compare {selectedIds.length}
			</Button>
			<Button variant="ghost" onclick={clearSelection} size="sm">Clear</Button>
		{/if}
	</div>

	{#if filteredItems.length === 0}
		<EmptyState icon="📊" title="No media yet" message="Admins can add YouTube and Spotify media from the admin panel." />
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each filteredItems as item (item.id)}
				{@const freshness = formatFreshness(item.metrics_last_fetched_at, 10)}
				<div
					class="panel overflow-hidden p-0 block hover:border-accent transition-colors relative {borderClass(item.media_type)} {compareMode ? (selectedIds.includes(item.id) ? 'ring-2 ring-accent' : 'opacity-50') : ''}"
				>
					{#if compareMode}
						<button
							type="button"
							class="absolute top-2 right-2 z-10 w-6 h-6 rounded border-2 flex items-center justify-center {selectedIds.includes(item.id) ? 'bg-accent border-accent text-white' : 'border-muted bg-panel'}"
							onclick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSelect(item.id); }}
							data-testid="media-select-check"
						>
							{#if selectedIds.includes(item.id)}✓{/if}
						</button>
					{/if}
					<a
						href={compareMode ? '#' : `${base}/media/${item.id}`}
						{...(compareMode ? { onclick: (e: MouseEvent) => { e.preventDefault(); toggleSelect(item.id); } } : {})}
						class="block no-underline"
						data-testid="media-card"
					>
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
							<div class="flex items-center justify-between text-xs mb-1">
								<RelativeTime datetime={item.published_at} short testId="media-published" />
							</div>
							<div class="grid grid-cols-3 gap-1 text-xs" data-testid="media-metrics">
								<span class="text-muted truncate">👁️ <span class="text-text font-mono">{formatNumber(metricValue(item, 'view_count'))}</span></span>
								<span class="text-muted truncate">👍 <span class="text-text font-mono">{formatNumber(metricValue(item, 'like_count'))}</span></span>
								<span class="text-muted truncate">💬 <span class="text-text font-mono">{formatNumber(metricValue(item, 'comment_count'))}</span></span>
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
