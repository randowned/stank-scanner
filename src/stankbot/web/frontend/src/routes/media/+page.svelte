<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem, MetricDef, ProviderDef } from '$lib/types';
	import { providersByType, loadProviders } from '$lib/stores';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Tabs from '$lib/components/Tabs.svelte';
	import Button from '$lib/components/Button.svelte';
	import SelectDropdown from '$lib/components/SelectDropdown.svelte';
	import RelativeTime from '$lib/components/RelativeTime.svelte';

	let { data } = $props();

	const items = $derived(data.items as MediaItem[]);
	const providers = $derived((data.providers as ProviderDef[]) ?? []);

	$effect(() => {
		if (providers.length > 0) {
			const map: Record<string, ProviderDef> = {};
			for (const p of providers) map[p.type] = p;
			providersByType.set(map);
		}
	});

	void loadProviders();

	let activeType = $state<string>('');
	let compareMode = $state(false);
	let selectedIds = $state<number[]>([]);
	let selectedMediaType = $state<string | null>(null);
	let searchQuery = $state<string>('');
	let sortKey = $state<string>('published_desc');

	const typeTabs = [
		{ value: '', label: 'All' },
		{ value: 'youtube', label: 'YouTube' },
		{ value: 'spotify', label: 'Spotify' }
	];

	const sortOptions = [
		{ value: 'published_desc', label: 'Newest', icon: '🆕' },
		{ value: 'published_asc', label: 'Oldest', icon: '📜' },
		{ value: 'updated_desc', label: 'Recently updated', icon: '🔄' },
		{ value: 'views_desc', label: 'Most popular', icon: '🔥' },
		{ value: 'title_asc', label: 'A → Z', icon: '🔤' }
	];

	function primaryMetricValue(item: MediaItem): number {
		const provider = $providersByType[item.media_type];
		const key = provider?.metrics?.[0]?.key ?? 'view_count';
		return item.metrics?.[key]?.value ?? 0;
	}

	const filteredItems = $derived.by(() => {
		let list = activeType ? items.filter((i) => i.media_type === activeType) : items;
		const q = searchQuery.trim().toLowerCase();
		if (q) {
			list = list.filter(
				(i) =>
					i.title.toLowerCase().includes(q) ||
					(i.channel_name ?? '').toLowerCase().includes(q)
			);
		}
		const sorted = [...list];
		const ts = (s: string | null) => (s ? new Date(s).getTime() : 0);
		switch (sortKey) {
			case 'published_asc':
				sorted.sort((a, b) => ts(a.published_at) - ts(b.published_at));
				break;
			case 'updated_desc':
				sorted.sort((a, b) => ts(b.metrics_last_fetched_at) - ts(a.metrics_last_fetched_at));
				break;
			case 'views_desc':
				sorted.sort((a, b) => primaryMetricValue(b) - primaryMetricValue(a));
				break;
			case 'title_asc':
				sorted.sort((a, b) => a.title.localeCompare(b.title));
				break;
			case 'published_desc':
			default:
				sorted.sort((a, b) => ts(b.published_at) - ts(a.published_at));
		}
		return sorted;
	});

	function borderClass(type: string): string {
		if (type === 'youtube') return 'border-l-[3px] border-l-[#ff0000]/70';
		if (type === 'spotify') return 'border-l-[3px] border-l-[#1db954]/70';
		return '';
	}

	function metricValue(item: MediaItem, key: string): number {
		return item.metrics?.[key]?.value ?? 0;
	}

	function formatMetric(m: MetricDef, value: number): string {
		if (m.format === 'percentage') return `${Math.round(value)}%`;
		if (m.format === 'duration') {
			const mins = Math.floor(value / 60);
			const secs = Math.floor(value % 60);
			return `${mins}:${String(secs).padStart(2, '0')}`;
		}
		return formatNumber(value);
	}

	function metricsForCard(item: MediaItem): Array<{ key: string; label: string; icon: string; display: string }> {
		const provider = $providersByType[item.media_type];
		const out: Array<{ key: string; label: string; icon: string; display: string }> = [];
		if (provider) {
			for (const m of provider.metrics) {
				out.push({
					key: m.key,
					label: m.label,
					icon: m.icon || '📊',
					display: formatMetric(m, metricValue(item, m.key))
				});
			}
		} else {
			out.push(
				{ key: 'view_count', label: 'Views', icon: '👁️', display: formatNumber(metricValue(item, 'view_count')) },
				{ key: 'like_count', label: 'Likes', icon: '👍', display: formatNumber(metricValue(item, 'like_count')) },
				{ key: 'comment_count', label: 'Comments', icon: '💬', display: formatNumber(metricValue(item, 'comment_count')) }
			);
		}
		// Pad Spotify cards with duration and release year as filler chips
		if (item.media_type === 'spotify' && out.length < 3) {
			if (item.duration_seconds != null) {
				const mins = Math.floor(item.duration_seconds / 60);
				const secs = item.duration_seconds % 60;
				out.push({ key: '_duration', label: 'Duration', icon: '⏱️', display: `${mins}:${String(secs).padStart(2, '0')}` });
			}
			if (item.published_at) {
				const year = new Date(item.published_at).getFullYear();
				if (Number.isFinite(year)) {
					out.push({ key: '_year', label: 'Released', icon: '📅', display: String(year) });
				}
			}
		}
		return out.slice(0, 3);
	}

	function toggleSelect(id: number) {
		if (selectedIds.includes(id)) {
			selectedIds = selectedIds.filter((sid) => sid !== id);
			if (selectedIds.length === 0) {
				selectedMediaType = null;
			}
		} else {
			const item = items.find((i) => i.id === id);
			if (item && selectedIds.length === 0) {
				selectedMediaType = item.media_type;
			}
			selectedIds = [...selectedIds, id];
		}
	}

	function clearSelection() {
		selectedIds = [];
		selectedMediaType = null;
	}

	function compareSelected() {
		if (selectedIds.length < 2) return;
		const primary = selectedIds[0];
		const extras = selectedIds.slice(1);
		// Pick a metric all selected items share, falling back to view_count
		const selected = items.filter((i) => selectedIds.includes(i.id));
		const types = new Set(selected.map((i) => i.media_type));
		let metric = 'view_count';
		if (types.size === 1) {
			const t = [...types][0];
			const provider = $providersByType[t];
			metric = provider?.metrics?.[0]?.key ?? 'view_count';
		}
		void goto(`${base}/media/${primary}?compare=${extras.join(',')}&metric=${metric}&days=7`);
	}

	const showCompareBtn = $derived(filteredItems.length > 1);
</script>

<div class="p-4 space-y-4">
	<PageHeader title="Media" subtitle="Media analytics" />

	<Tabs tabs={typeTabs} bind:value={activeType} />

	<div class="flex flex-wrap items-center gap-2">
		<input
			type="text"
			bind:value={searchQuery}
			placeholder="Search title or channel…"
			class="px-3 py-1.5 text-sm rounded border border-border bg-panel text-text placeholder:text-muted focus:outline-none focus:border-accent w-full sm:w-64"
			data-testid="media-search"
		/>
		<SelectDropdown options={sortOptions} bind:value={sortKey} testId="media-sort" />
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
				{@const cardMetrics = metricsForCard(item)}
				{@const typeLocked = compareMode && selectedMediaType !== null && item.media_type !== selectedMediaType}
				<div
					class="panel overflow-hidden p-0 block hover:border-accent transition-colors relative {borderClass(item.media_type)} {compareMode ? (selectedIds.includes(item.id) ? 'ring-2 ring-accent' : typeLocked ? 'opacity-30 pointer-events-none cursor-not-allowed' : 'opacity-50') : ''}"
				>
					{#if compareMode}
						<button
							type="button"
							class="absolute top-2 right-2 z-10 w-6 h-6 rounded border-2 flex items-center justify-center {selectedIds.includes(item.id) ? 'bg-accent border-accent text-white' : 'border-muted bg-panel'} {typeLocked ? 'pointer-events-none' : ''}"
							onclick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSelect(item.id); }}
							data-testid="media-select-check"
							disabled={typeLocked}
						>
							{#if selectedIds.includes(item.id)}✓{/if}
						</button>
					{/if}
					<a
						href={compareMode && !typeLocked ? '#' : `${base}/media/${item.id}`}
						{...(compareMode && !typeLocked ? { onclick: (e: MouseEvent) => { e.preventDefault(); toggleSelect(item.id); } } : {})}
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
							<div class="grid gap-1 text-xs" style="grid-template-columns: repeat({Math.max(1, cardMetrics.length)}, minmax(0, 1fr));" data-testid="media-metrics">
								{#each cardMetrics as m (m.key)}
									<span class="text-muted truncate" title={m.label}>{m.icon} <span class="text-text font-mono">{m.display}</span></span>
								{/each}
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
