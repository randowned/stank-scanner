<script lang="ts">
	import { apiFetch, apiPost, apiDelete } from '$lib/api';
	import { toErrorMessage } from '$lib/api-utils';
	import { formatNumber, formatFreshness } from '$lib/format';
	import type { MediaItem, ProviderDef } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Tabs from '$lib/components/Tabs.svelte';
	import Button from '$lib/components/Button.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import SelectDropdown from '$lib/components/SelectDropdown.svelte';
	import Toggle from '$lib/components/Toggle.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { base } from '$app/paths';

	let items = $state<MediaItem[]>([]);
	let providers = $state<ProviderDef[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let activeType = $state<string>('');

	let settingsOpen = $state(false);
	let youtubeInterval = $state(60);
	let spotifyInterval = $state(60);
	let ephemeralEnabled = $state(true);
	let adminOnly = $state(false);
	let enabledProviders = $state<string[]>(['youtube', 'spotify']);
	let savingSettings = $state(false);
	let settingsError = $state<string | null>(null);

	let deleteOpen = $state(false);
	let deletingId = $state<number | null>(null);
	let deletingTitle = $state('');

	let refreshAllOpen = $state(false);

	const typeTabs = $derived([
		{ value: '', label: 'All' },
		...providers.map((p) => ({ value: p.type, label: p.label }))
	]);

	async function loadItems() {
		loading = true;
		error = null;
		try {
			const res = await apiFetch<{ items: MediaItem[] }>('/api/admin/media');
			items = res.items;
		} catch (err) {
			error = toErrorMessage(err, 'Failed to load media');
		} finally {
			loading = false;
		}
	}

	async function loadProviders() {
		try {
			const res = await apiFetch<{ providers: ProviderDef[] }>('/api/admin/media/providers');
			providers = res.providers;
		} catch {
			// providers optional
		}
	}

	const VALID_INTERVALS = [1, 5, 15, 30, 45, 60, 120, 240, 720, 1440] as const;

	const intervalOptions = [
		{ value: 1, label: '1 minute', icon: '⏱️' },
		{ value: 5, label: '5 minutes', icon: '⏱️' },
		{ value: 15, label: '15 minutes', icon: '⏱️' },
		{ value: 30, label: '30 minutes', icon: '⏱️' },
		{ value: 45, label: '45 minutes', icon: '⏱️' },
		{ value: 60, label: '1 hour', icon: '⏱️' },
		{ value: 120, label: '2 hours', icon: '⏱️' },
		{ value: 240, label: '4 hours', icon: '⏱️' },
		{ value: 720, label: '12 hours (2× daily)', icon: '⏱️' },
		{ value: 1440, label: '24 hours (daily)', icon: '⏱️' },
	];

	async function loadSettings() {
		try {
			const res = await apiFetch<{ values: Record<string, unknown> }>('/api/admin/settings');
			const ytVal = res.values?.['media_youtube_update_interval_minutes'];
			if (typeof ytVal === 'number') {
				youtubeInterval = VALID_INTERVALS.find(iv => iv >= ytVal) ?? 60;
			}
			const spVal = res.values?.['media_spotify_update_interval_minutes'];
			if (typeof spVal === 'number') {
				spotifyInterval = VALID_INTERVALS.find(iv => iv >= spVal) ?? 60;
			}
			if (typeof res.values?.['media_replies_ephemeral'] === 'boolean') {
				ephemeralEnabled = res.values?.['media_replies_ephemeral'] as boolean;
			}
			if (typeof res.values?.['media_replies_admin_only'] === 'boolean') {
				adminOnly = res.values?.['media_replies_admin_only'] as boolean;
			}
			const prov = res.values?.['media_providers_enabled'];
			if (Array.isArray(prov)) {
				enabledProviders = prov as string[];
			}
		} catch {
			// keep defaults
		}
	}

	async function saveSettings() {
		savingSettings = true;
		settingsError = null;
		try {
			await apiPost('/api/admin/media/settings', {
				youtube_interval_minutes: youtubeInterval,
				spotify_interval_minutes: spotifyInterval,
				replies_ephemeral: ephemeralEnabled,
				admin_only: adminOnly,
				providers_enabled: enabledProviders
			});
			settingsOpen = false;
		} catch (err) {
			settingsError = toErrorMessage(err, 'Failed to save');
		} finally {
			savingSettings = false;
		}
	}

	async function handleDelete() {
		if (deletingId === null) return;
		try {
			await apiDelete(`/api/admin/media/${deletingId}`);
			deleteOpen = false;
			deletingId = null;
			await loadItems();
		} catch (err) {
			error = toErrorMessage(err, 'Failed to delete');
		}
	}

	async function handleRefresh(mediaId: number) {
		try {
			await apiPost(`/api/admin/media/${mediaId}/refresh`);
			await loadItems();
		} catch (err) {
			error = toErrorMessage(err, 'Failed to refresh');
		}
	}

	async function handleRefreshAll() {
		try {
			await apiPost('/api/admin/media/refresh-all');
			refreshAllOpen = false;
			await loadItems();
		} catch (err) {
			error = toErrorMessage(err, 'Failed to refresh all');
		}
	}

	function openDelete(id: number, title: string) {
		deletingId = id;
		deletingTitle = title;
		deleteOpen = true;
	}

	async function handleBackfill() {
		try {
			const res = await apiPost<{ updated: number }>('/api/admin/media/backfill-alignment-mask');
			alert(`Backfilled ${res.updated} snapshots.`);
		} catch (err) {
			alert(`Backfill failed: ${toErrorMessage(err, 'Unknown error')}`);
		}
	}

	$effect(() => {
		loadItems();
		loadProviders();
		loadSettings();
	});

	const providersByType = $derived(
		Object.fromEntries(providers.map((p) => [p.type, p]))
	);

	const filteredItems = $derived(
		activeType ? items.filter((i) => i.media_type === activeType) : items
	);

	function primaryMetric(item: MediaItem): { key: string; label: string } {
		const p = providersByType[item.media_type];
		const m = p?.metrics?.[0];
		return { key: m?.key ?? 'view_count', label: m?.label ?? 'Views' };
	}

	function getEditUrl(id: number): string {
		return `${base}/admin/media/${id}/edit`;
	}

	function typeBadgeClass(type: string): string {
		if (type === 'youtube') return 'bg-[#ff0000]/15 text-[#ff0000]';
		if (type === 'spotify') return 'bg-[#1db954]/15 text-[#1db954]';
		return 'bg-border text-muted';
	}

	function toggleProvider(type: string) {
		if (enabledProviders.includes(type)) {
			enabledProviders = enabledProviders.filter((t) => t !== type);
		} else {
			enabledProviders = [...enabledProviders, type];
		}
	}
</script>

<PageHeader title="Media" subtitle="Manage media items for the dashboard">
	{#snippet actions()}
		<Button variant="secondary" onclick={() => (settingsOpen = true)} testId="media-settings-btn">
			⚙️
		</Button>
		<Button variant="secondary" onclick={() => (refreshAllOpen = true)} testId="media-refresh-all-btn">
			Refresh all
		</Button>
		<a href="{base}/admin/media/add" class="no-underline">
			<Button variant="primary" testId="media-add-btn">Add media</Button>
		</a>
	{/snippet}
</PageHeader>

<Tabs tabs={typeTabs} bind:value={activeType} />

{#if error}
	<div class="panel border-red-500/50 mb-4">
		<div class="text-red-400 text-sm">{error}</div>
	</div>
{/if}

{#if loading}
	<div class="space-y-2" data-testid="media-admin-skeleton">
		{#each Array(3) as _}
			<div class="panel animate-pulse flex items-center gap-3">
				<div class="w-20 h-12 bg-border rounded shrink-0"></div>
				<div class="flex-1">
					<div class="h-4 bg-border rounded w-48 mb-2"></div>
					<div class="h-3 bg-border rounded w-32"></div>
				</div>
			</div>
		{/each}
	</div>
{:else if filteredItems.length === 0}
	<EmptyState icon="🎬" title="No media" message="Add your first media item to start tracking metrics." />
{:else}
	<div class="space-y-4">
		{#each filteredItems as item (item.id)}
			{@const freshness = formatFreshness(item.metrics_last_fetched_at, item.media_type === 'spotify' ? spotifyInterval : youtubeInterval)}
			{@const primary = primaryMetric(item)}
			<div class="bg-panel border border-border rounded-lg overflow-hidden flex flex-col md:flex-row md:items-stretch" data-testid="media-admin-row">
				{#if item.thumbnail_url}
					<img src={item.thumbnail_url} alt={item.title} class="w-full md:w-24 h-auto md:min-h-[4.5rem] object-cover shrink-0" loading="lazy" />
				{:else}
					<div class="w-full md:w-24 min-h-[3rem] md:min-h-[4.5rem] bg-border shrink-0 flex items-center justify-center text-lg">▶️</div>
				{/if}
				<div class="flex flex-row flex-auto">
					<div class="flex-1 min-w-0 p-3">
						<div class="font-medium text-sm truncate">{item.title}</div>
						<div class="text-xs text-muted">{item.channel_name ?? '—'}</div>
						<div class="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1">
							<span class="text-xs px-1.5 py-0.5 rounded capitalize {typeBadgeClass(item.media_type)}">{item.media_type}</span>
							{#if item.name}<span class="text-xs text-muted font-mono">📛 {item.name}</span>{/if}
							<span class="text-xs text-muted">{primary.label}: {formatNumber(item.metrics?.[primary.key]?.value ?? 0)}</span>
							<span class="text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}">
								{freshness.label}
							</span>
						</div>
					</div>
					<div class="flex items-center justify-end gap-1 shrink-0 p-3 max-md:border-t max-md:border-border">
						<Button variant="ghost" onclick={() => handleRefresh(item.id)} testId="media-refresh-btn">↻</Button>
						<a href={getEditUrl(item.id)} class="no-underline">
							<Button variant="ghost" testId="media-edit-btn">Edit</Button>
						</a>
						<Button variant="ghost" onclick={() => openDelete(item.id, item.title)} testId="media-delete-btn">🗑</Button>
					</div>
				</div>
			</div>
		{/each}
	</div>
{/if}

<!-- Settings Modal -->
<Modal bind:open={settingsOpen} title="Media Settings">
	<div class="space-y-5">
		<!-- General -->
		<div>
			<h3 class="text-sm font-semibold mb-3">General</h3>
			<div class="space-y-3">
				<div>
					<Toggle bind:checked={ephemeralEnabled} label="Ephemeral /stats replies" disabled={savingSettings} />
					<div class="text-xs text-muted mt-1">When enabled, command responses are visible only to the caller.</div>
				</div>
				<div>
					<Toggle bind:checked={adminOnly} label="Admin-only /stats commands" disabled={savingSettings} />
					<div class="text-xs text-muted mt-1">When enabled, only admins may use /stats commands.</div>
				</div>
			</div>
		</div>

		<!-- Providers -->
		<div>
			<h3 class="text-sm font-semibold mb-3">Providers</h3>
			<div class="space-y-4">
				<!-- YouTube -->
				<div class="bg-surface/30 rounded-lg p-3 space-y-3">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium">▶️ YouTube</span>
						<label class="inline-flex items-center gap-1.5 cursor-pointer select-none">
							<input type="checkbox" checked={enabledProviders.includes('youtube')} onchange={() => toggleProvider('youtube')} class="accent-accent" />
							<span class="text-xs text-muted">Enabled</span>
						</label>
					</div>
					<div class="flex items-center justify-between gap-3">
						<span class="text-xs text-muted">Update interval</span>
						<SelectDropdown options={intervalOptions} bind:value={youtubeInterval} disabled={savingSettings} testId="media-interval-youtube" />
					</div>
				</div>

				<!-- Spotify -->
				<div class="bg-surface/30 rounded-lg p-3 space-y-3">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium">🟢 Spotify</span>
						<label class="inline-flex items-center gap-1.5 cursor-pointer select-none">
							<input type="checkbox" checked={enabledProviders.includes('spotify')} onchange={() => toggleProvider('spotify')} class="accent-accent" />
							<span class="text-xs text-muted">Enabled</span>
						</label>
					</div>
					<div class="flex items-center justify-between gap-3">
						<span class="text-xs text-muted">Update interval</span>
						<SelectDropdown options={intervalOptions} bind:value={spotifyInterval} disabled={savingSettings} testId="media-interval-spotify" />
					</div>
				</div>
			</div>
			<div class="text-xs text-muted mt-1">Fetches are aligned to clock boundaries. Disabled providers are hidden from everyone.</div>
		</div>

		<!-- Operations -->
		<div class="pt-2 border-t border-border">
			<h3 class="text-sm font-semibold mb-2">Operations</h3>
			<Button variant="secondary" onclick={handleBackfill} testId="media-backfill-alignment">Backfill alignment masks</Button>
			<div class="text-xs text-muted mt-1">Computes alignment masks for all existing snapshots. Run once after deploying the alignment_mask migration.</div>
		</div>

		{#if settingsError}
			<div class="text-red-400 text-sm">{settingsError}</div>
		{/if}
		<div class="flex justify-end gap-2 pt-2">
			<Button variant="secondary" onclick={() => (settingsOpen = false)} testId="media-settings-cancel">Cancel</Button>
			<Button variant="primary" onclick={saveSettings} loading={savingSettings} testId="media-settings-save">Save</Button>
		</div>
	</div>
</Modal>

<!-- Refresh All Confirm -->
<ConfirmDialog
	bind:open={refreshAllOpen}
	title="Refresh all media?"
	body="This will fetch metrics for every media item from their providers."
	confirmLabel="Refresh all"
	onconfirm={handleRefreshAll}
/>

<!-- Delete Confirm -->
<ConfirmDialog
	bind:open={deleteOpen}
	title="Delete media?"
	body="Delete &quot;{deletingTitle}&quot;? This also removes all cached metrics and history."
	confirmLabel="Delete"
	danger={true}
	onconfirm={handleDelete}
/>
