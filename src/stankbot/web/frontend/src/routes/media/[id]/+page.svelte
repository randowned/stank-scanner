<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { apiFetch } from '$lib/api';
	import { formatFreshness } from '$lib/format';
	import type { MediaItem, MetricSnapshot, CompareData, MetricDef, ProviderDef } from '$lib/types';
	import { providersByType, loadProviders, mediaMetricUpdates } from '$lib/stores';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import SelectDropdown from '$lib/components/SelectDropdown.svelte';
	import Button from '$lib/components/Button.svelte';
	import Chart from '$lib/components/Chart.svelte';
	import RelativeTime from '$lib/components/RelativeTime.svelte';

	let { data } = $props();

	const item = $derived(data.item as MediaItem | null);
	const providers = $derived((data.providers as ProviderDef[]) ?? []);

	$effect(() => {
		if (providers.length > 0) {
			const map: Record<string, ProviderDef> = {};
			for (const p of providers) map[p.type] = p;
			providersByType.set(map);
		}
	});

	void loadProviders();

	const provider = $derived(
		item ? (providers.find(p => p.type === item.media_type) ?? $providersByType[item.media_type]) : undefined
	);
	const providerMetrics = $derived<MetricDef[]>(provider?.metrics ?? []);

	// ---- state initialized from URL params or defaults -------------------

	function readURLParams(): {
		metric: string; hours: number; resolution: string; mode: 'delta' | 'total'; compareIds: string[];
	} {
		const sp = $page.url.searchParams;
		const metric = sp.get('metric') || (item?.media_type === 'spotify' ? 'playcount' : 'view_count');
		const hoursStr = sp.get('hours');
		const daysStr = sp.get('days');
		let hours: number;
		if (hoursStr !== null) {
			hours = Number(hoursStr) || 24;
		} else if (daysStr !== null) {
			hours = (Number(daysStr) || 1) * 24;
		} else {
			hours = 48;
		}
		const resolution = sp.get('resolution') || 'auto';
		const mode = (sp.get('mode') === 'total' ? 'total' : 'delta') as 'delta' | 'total';
		const compareRaw = sp.get('compare') || '';
		const compareIds = compareRaw
			? compareRaw.split(',').map((s) => s.trim()).filter(Boolean).filter((id) => id !== String(data.mediaId))
			: [];
		return { metric, hours, resolution, mode, compareIds };
	}

	function updateURL() {
		if (!item) return;
		const url = new URL(window.location.href);
		url.searchParams.set('metric', selectedMetric);
		if (selectedHours < 24) {
			url.searchParams.set('hours', String(selectedHours));
			url.searchParams.delete('days');
		} else {
			url.searchParams.set('days', String(Math.max(1, Math.round(selectedHours / 24))));
			url.searchParams.delete('hours');
		}
		if (selectedAggregation !== 'auto') {
			url.searchParams.set('resolution', selectedAggregation);
		} else {
			url.searchParams.delete('resolution');
		}
		if (comparisonMode !== 'delta') {
			url.searchParams.set('mode', comparisonMode);
		} else {
			url.searchParams.delete('mode');
		}
		if (compareIds.length > 0) {
			url.searchParams.set('compare', compareIds.join(','));
		} else {
			url.searchParams.delete('compare');
		}
		url.searchParams.sort();
		window.history.replaceState(window.history.state, '', url.toString());
	}

	const initial = readURLParams();
	let selectedMetric = $state<string>(initial.metric);
	let selectedHours = $state<number>(initial.hours);
	let selectedAggregation = $state<string>(initial.resolution);

	// align selected metric with provider once providers load
	$effect(() => {
		if (providerMetrics.length > 0 && !providerMetrics.some((m) => m.key === selectedMetric)) {
			selectedMetric = providerMetrics[0].key;
		}
	});
	let comparisonMode = $state<'delta' | 'total'>(initial.mode);
	let compareIds = $state<string[]>(initial.compareIds);

	let history = $state<MetricSnapshot[]>([]);
	let compareData = $state<CompareData | null>(null);
	let loadingHistory = $state(false);
	let loadingCompare = $state(false);
	let currentHistoryUrl = $state('');
	let _prevDatasets: { label: string; data: { x: number; y: number }[] }[] = [];

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
		{ value: 1, label: '1 hour', icon: '⏱️' },
		{ value: 6, label: '6 hours', icon: '⏱️' },
		{ value: 12, label: '12 hours', icon: '⏱️' },
		{ value: 24, label: '24h', icon: '📅' },
		{ value: 48, label: '48h', icon: '📅' },
		{ value: 24 * 7, label: '7 days', icon: '📅' },
		{ value: 24 * 30, label: '30 days', icon: '📅' },
		{ value: 24 * 90, label: '90 days', icon: '📅' },
		{ value: 24 * 365, label: '1 year', icon: '📅' }
	];

	const viewOptions = [
		{ value: 'delta', label: 'Change', icon: 'Δ' },
		{ value: 'total', label: 'Cumulative', icon: 'Σ' }
	];

	const providerIntervalMs = $derived((provider?.interval_minutes ?? 1) * 60_000);

	const aggregationOptions = $derived.by(() => {
		const rangeHours = selectedHours;
		const minMs = providerIntervalMs;
		const all: Array<{ value: string; label: string; icon: string }> = [
			{ value: 'auto', label: 'Auto', icon: '🤖' },
			{ value: 'minutely', label: 'Min', icon: '🕐' },
			{ value: '5min', label: '5 Min', icon: '🕐' },
			{ value: '15min', label: '15 Min', icon: '🕐' },
			{ value: '30min', label: '30 Min', icon: '🕐' },
			{ value: 'hourly', label: 'Hourly', icon: '⏱️' },
			{ value: 'daily', label: 'Daily', icon: '📅' },
			{ value: 'weekly', label: 'Weekly', icon: '📆' },
			{ value: 'monthly', label: 'Monthly', icon: '🗓️' },
		];
		const bucketMs: Record<string, number> = {
			minutely: 60_000,
			'5min': 300_000,
			'15min': 900_000,
			'30min': 1_800_000,
			hourly: 3_600_000,
			daily: 86_400_000,
			weekly: 604_800_000,
			monthly: 2_592_000_000,
		};
		return all.filter(
			(o) =>
				o.value === 'auto' ||
				((bucketMs[o.value] ?? 0) * 2 < rangeHours * 3_600_000 &&
					(bucketMs[o.value] ?? 0) >= minMs)
		);
	});

	const hasCompare = $derived(compareIds.length > 0);

	const dataStart = $derived(history.length > 0 ? new Date(history[0].fetched_at).getTime() : 0);
	const rangeStart = $derived(Date.now() - selectedHours * 3600 * 1000);
	const dataShorter = $derived(
		dataStart > 0 && dataStart > rangeStart + selectedHours * 3_600_000 * 0.1
	);

	const dataStartLabel = $derived(
		dataShorter && dataStart > 0
			? new Date(dataStart).toLocaleString('en-US', selectedHours <= 48
				? { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
				: { month: 'short', day: 'numeric', year: 'numeric' })
			: ''
	);

	const chartMinUnit = $derived.by<'minute' | 'hour' | 'day' | 'week' | 'month' | undefined>(() => {
		const bms = resolutionBucketMs;
		if (bms === null) return undefined;
		if (bms < 3_600_000) return 'minute';
		if (bms < 86_400_000) return 'hour';
		if (bms < 604_800_000) return 'day';
		if (bms < 2_592_000_000) return 'week';
		return 'month';
	});

	function bucketDeltas(points: { x: number; y: number }[], bucketMs: number): { x: number; y: number }[] {
		if (points.length === 0 || bucketMs <= 0) return points;
		const buckets: Record<number, number> = {};
		for (const p of points) {
			const bucketStart = Math.floor(p.x / bucketMs) * bucketMs;
			buckets[bucketStart] = (buckets[bucketStart] ?? 0) + p.y;
		}
		const now = Date.now();
		return Object.entries(buckets)
			.map(([k, v]) => ({ x: Number(k), y: v }))
			.filter((p) => p.x + bucketMs <= now)
			.sort((a, b) => a.x - b.x);
	}

	function bucketCumulative(points: { x: number; y: number }[], bucketMs: number): { x: number; y: number }[] {
		if (points.length === 0 || bucketMs <= 0) return points;
		const buckets: Record<number, number> = {};
		for (const p of points) {
			const bucketStart = Math.floor(p.x / bucketMs) * bucketMs;
			if (buckets[bucketStart] === undefined || p.y > buckets[bucketStart]) {
				buckets[bucketStart] = p.y;
			}
		}
		return Object.entries(buckets)
			.map(([k, v]) => ({ x: Number(k), y: v }))
			.sort((a, b) => a.x - b.x);
	}

	const _AGG_BUCKET_MS: Record<string, number> = {
		minutely: 60_000,
		'5min': 300_000,
		'15min': 900_000,
		'30min': 1_800_000,
		hourly: 3_600_000,
		daily: 86_400_000,
		weekly: 604_800_000,
		monthly: 2_592_000_000,
	};

	function autoResolutionMs(rangeHours: number, minIntervalMs: number): number | null {
		if (rangeHours <= 0) return null;
		const rangeMs = rangeHours * 3_600_000;
		const idealBucketMs = rangeMs / 24;
		const buckets = [60_000, 300_000, 900_000, 1_800_000, 3_600_000, 86_400_000, 604_800_000, 2_592_000_000];
		const eligible = buckets.filter((b) => b >= minIntervalMs && b * 2 < rangeMs);
		return eligible.find((b) => b >= idealBucketMs) ?? eligible[eligible.length - 1] ?? null;
	}

	const resolutionBucketMs = $derived(
		selectedAggregation === 'auto'
			? autoResolutionMs(selectedHours, providerIntervalMs)
			: (_AGG_BUCKET_MS[selectedAggregation] ?? null)
	);

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

	function formatDetailedNumber(n: number): string {
		return n.toLocaleString('en-US');
	}

	function formatMetricValue(key: string, value: number): string {
		const m = providerMetrics.find((mm) => mm.key === key);
		if (m?.format === 'percentage') return `${Math.round(value)}%`;
		if (m?.format === 'duration') {
			const mins = Math.floor(value / 60);
			const secs = Math.floor(value % 60);
			return `${mins}:${String(secs).padStart(2, '0')}`;
		}
		return formatDetailedNumber(value);
	}

	function metricValue(key: string): number {
		return item?.metrics?.[key]?.value ?? 0;
	}

	const serverAggregations = new Set(['5min', '15min', '30min', 'hourly', 'daily', 'weekly', 'monthly']);

	const resolvedAggregation = $derived.by(() => {
		if (selectedAggregation !== 'auto') return selectedAggregation;
		if (resolutionBucketMs === null) return null;
		return Object.entries(_AGG_BUCKET_MS).find(
			([k, ms]) => ms === resolutionBucketMs && serverAggregations.has(k)
		)?.[0] ?? null;
	});

	const useServerAggregation = $derived(serverAggregations.has(resolvedAggregation ?? ''));

	// Auto-default to delta when entering/leaving compare mode
	let prevHasCompare = $state(false);
	$effect(() => {
		const now = compareIds.length > 0;
		if (now !== prevHasCompare) {
			comparisonMode = 'delta';
			prevHasCompare = now;
		}
	});

	function buildChartUrl(): string {
		if (!item) return '';
		let url: string;
		if (selectedHours < 24) {
			url = `/api/media/${item.id}/history?metric=${selectedMetric}&hours=${selectedHours}`;
		} else {
			const days = Math.max(1, Math.round(selectedHours / 24));
			url = `/api/media/${item.id}/history?metric=${selectedMetric}&days=${days}`;
		}
		if (useServerAggregation) {
			url += `&aggregation=${resolvedAggregation}&mode=${comparisonMode}`;
		}
		if (compareIds.length > 0) {
			url += `&compare_ids=${compareIds.join(',')}`;
		}
		return url;
	}

	async function loadChartData() {
		if (!item) return;
		const url = buildChartUrl();
		loadingHistory = true;
		loadingCompare = compareIds.length > 0;
		try {
			const res = await apiFetch<{ history: MetricSnapshot[]; compare?: CompareData }>(url);
			history = res.history;
			compareData = res.compare ?? null;
			currentHistoryUrl = url;
		} catch {
			history = [];
			compareData = null;
			currentHistoryUrl = url;
		} finally {
			loadingHistory = false;
			loadingCompare = false;
		}
	}

	// fetch chart data whenever params change
	$effect(() => {
		void selectedMetric;
		void selectedHours;
		void comparisonMode;
		void selectedAggregation;

		if (!aggregationOptions.some((o) => o.value === selectedAggregation)) {
			selectedAggregation = 'auto';
			return;
		}

		const _ssnap = history;
		if (_ssnap.length > 0 && _prevDatasets.length === 0) {
			_prevDatasets = [{
				label: item?.name ?? metricLabel(selectedMetric),
				data: _ssnap.map(h => ({ x: new Date(h.fetched_at).getTime(), y: h.value }))
			}];
		}

		void loadChartData();
		updateURL();
	});

	function clearComparison() {
		compareIds = [];
		compareData = null;
	}

	function buildChartDatasets() {
		if (hasCompare && compareData && item) {
			const bms = !useServerAggregation ? resolutionBucketMs : null;
			return compareData.series
				.filter((s) => s.media_type === item.media_type)
				.map((s) => {
					let points = s.points.map((p) => ({
						x: new Date(String(p.x)).getTime(),
						y: p.y
					}));
					if (bms !== null) {
						points = comparisonMode === 'delta'
							? bucketDeltas(points, bms)
							: bucketCumulative(points, bms);
					}
					return {
						label: s.media_item_id === item.id ? (item.name || s.title) : (s.name || s.title),
						data: points
					};
				});
		}
		if (buildChartUrl() !== currentHistoryUrl) {
			return _prevDatasets;
		}
		let result: { label: string; data: { x: number; y: number }[] }[];
		if (useServerAggregation) {
			result = [{
				label: item?.name || metricLabel(selectedMetric),
				data: history.map((h) => ({
					x: new Date(h.fetched_at).getTime(),
					y: h.value
				}))
			}];
		} else {
			let points = history.map((h) => ({
				x: new Date(h.fetched_at).getTime(),
				y: h.value
			}));
			if (comparisonMode === 'delta' && points.length >= 2) {
				let prev = points[0].y;
				for (const p of points) {
					const cur = p.y;
					p.y = cur - prev;
					prev = cur;
				}
				points.shift();
				if (resolutionBucketMs !== null) {
					points = bucketDeltas(points, resolutionBucketMs);
				}
			} else if (comparisonMode === 'delta') {
				points.length = 0;
			} else if (resolutionBucketMs !== null) {
				points = bucketCumulative(points, resolutionBucketMs);
			}
			result = [{
				label: item?.name || metricLabel(selectedMetric),
				data: points
			}];
		}
		_prevDatasets = result;
		return result;
	}

	function timeDisplayFormats() {
		return {
			millisecond: 'HH:mm:ss',
			second: 'HH:mm:ss',
			minute: 'HH:mm',
			hour: 'MMM d HH:mm',
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
		const timeScaleOpts: Record<string, unknown> = {
			tooltipFormat: 'MMM d, yyyy HH:mm',
			displayFormats: timeDisplayFormats()
		};
		if (chartMinUnit) {
			timeScaleOpts.minUnit = chartMinUnit;
		}
		return {
			datasets: { line: { spanGaps: true } },
			scales: {
				x: {
					type: 'time',
					time: timeScaleOpts,
					ticks: { maxTicksLimit: 8, color: '#9aa4b2', font: { size: 10 }, source: 'auto' },
					grid: { display: false }
				},
				y: {
					title: { display: false },
					...(isPercentage ? { min: 0, max: 100 } : { beginAtZero: false }),
					ticks: { callback: yTickCallback, color: '#9aa4b2', font: { size: 10 } },
					grid: { color: '#262a33', drawBorder: false }
				}
			},
			plugins: { legend: { display: compareData !== null && hasCompare } }
		};
	}

	// ---- live metric updates for StatTile flash ---------------------------

	let flashKeys = $state<Record<string, boolean>>({});
	$effect(() => {
		const updates = $mediaMetricUpdates;
		if (!updates.length || !item) return;
		const keys: Record<string, boolean> = {};
		for (const u of updates) {
			if (u.mediaItemId === item.id) {
				keys[u.metricKey] = true;
			}
		}
		if (Object.keys(keys).length > 0) {
			flashKeys = keys;
			setTimeout(() => { flashKeys = {}; }, 1500);
		}
	});

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
					{#if externalUrl()}
						<a
							href={externalUrl()}
							target="_blank"
							rel="noopener noreferrer"
							class="text-accent hover:underline"
							data-testid="media-external-link"
						>
							Open on {provider?.label ?? item.media_type} ↗
						</a>
					{/if}
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
							flash={!!flashKeys[opt.value]}
							testId="media-detail-{opt.value}"
							valueTestId="media-detail-{opt.value}-value"
							fontSize="md"
						/>
					{/each}
				</div>

				<div class="flex items-center gap-2 mb-3 flex-nowrap">
					<SelectDropdown options={metricOptions} bind:value={selectedMetric} testId="media-detail-metric" name="Metric" />
					<SelectDropdown options={rangeOptions} bind:value={selectedHours} testId="media-detail-range" name="Range" />
					<SelectDropdown options={aggregationOptions} bind:value={selectedAggregation} testId="media-detail-resolution" name="Resolution" />
					<SelectDropdown options={viewOptions} bind:value={comparisonMode} testId="media-detail-view" name="Mode" />
					{#if hasCompare}
						<Button variant="ghost" onclick={clearComparison} size="sm" testId="media-clear-compare" title="Clear comparison">✕</Button>
					{/if}
				</div>

				<div class="panel mb-4">
					<h3 class="text-sm font-semibold mb-2">
						{metricLabel(selectedMetric)}{comparisonMode === 'total' ? ' cumulative' : ' over time'}
						{#if dataStartLabel} <span class="text-xs text-muted font-normal">(data since {dataStartLabel})</span>{/if}
						{#if hasCompare && compareData}
							— comparing {buildChartDatasets().length} items
						{/if}
					</h3>
					{#if graphs}
						<div class={loadingHistory || loadingCompare ? 'opacity-60 transition-opacity' : ''} data-testid="media-detail-chart">
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
			</div>
		</div>
	</div>
{/if}
