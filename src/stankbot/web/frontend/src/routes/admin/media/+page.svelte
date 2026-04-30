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
	import Input from '$lib/components/Input.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { base } from '$app/paths';

	let items = $state<MediaItem[]>([]);
	let providers = $state<ProviderDef[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let activeType = $state<string>('');

	let settingsOpen = $state(false);
	let updateInterval = $state(10);
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
			const typeParam = activeType ? `?media_type=${activeType}` : '';
			const res = await apiFetch<{ items: MediaItem[] }>(`/api/admin/media${typeParam}`);
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

	async function loadSettings() {
		try {
			const res = await apiFetch<{ values: Record<string, unknown> }>('/api/admin/settings');
			const val = res.values?.['media_metrics_update_interval_minutes'];
			if (typeof val === 'number') updateInterval = val;
		} catch {
			// keep default
		}
	}

	async function saveSettings() {
		savingSettings = true;
		settingsError = null;
		try {
			await apiPost('/api/admin/media/settings', {
				update_interval_minutes: updateInterval
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

	$effect(() => {
		loadItems();
		loadProviders();
		loadSettings();
	});

	$effect(() => {
		if (activeType !== undefined) {
			loadItems();
		}
	});

	function getEditUrl(id: number): string {
		return `${base}/admin/media/${id}/edit`;
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
{:else if items.length === 0}
	<EmptyState icon="🎬" title="No media" message="Add your first media item to start tracking metrics." />
{:else}
	<div class="space-y-2">
		{#each items as item (item.id)}
			{@const freshness = formatFreshness(item.metrics_last_fetched_at, 10)}
			<div class="panel flex items-center gap-3" data-testid="media-admin-row">
				{#if item.thumbnail_url}
					<img src={item.thumbnail_url} alt={item.title} class="w-20 h-12 object-cover rounded shrink-0" loading="lazy" />
				{:else}
					<div class="w-20 h-12 bg-border rounded shrink-0 flex items-center justify-center text-lg">▶️</div>
				{/if}
				<div class="flex-1 min-w-0">
					<div class="font-medium text-sm truncate">{item.title}</div>
					<div class="text-xs text-muted">{item.channel_name ?? '—'}</div>
					<div class="flex items-center gap-2 mt-1">
					<span class="text-xs px-1.5 py-0.5 rounded bg-border text-muted capitalize">{item.media_type}</span>
					{#if item.slug}<span class="text-xs text-muted font-mono">📛 {item.slug}</span>{/if}
					<span class="text-xs text-muted">Views: {formatNumber(item.metrics?.view_count?.value ?? 0)}</span>
						<span class="text-xs {freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}">
							{freshness.label}
						</span>
					</div>
				</div>
				<div class="flex items-center gap-1 shrink-0">
					<Button variant="ghost" onclick={() => handleRefresh(item.id)} testId="media-refresh-btn">↻</Button>
					<a href={getEditUrl(item.id)} class="no-underline">
						<Button variant="ghost" testId="media-edit-btn">Edit</Button>
					</a>
					<Button variant="ghost" onclick={() => openDelete(item.id, item.title)} testId="media-delete-btn">🗑</Button>
				</div>
			</div>
		{/each}
	</div>
{/if}

<!-- Settings Modal -->
<Modal bind:open={settingsOpen} title="Media Settings">
	<div class="space-y-4">
		<div>
			<label class="block text-sm font-medium mb-1" for="media-interval-input">Metrics update interval (minutes)</label>
			<Input id="media-interval-input" type="number" bind:value={updateInterval} min={5} max={1440} disabled={savingSettings} />
			<div class="text-xs text-muted mt-1">Minimum 5 minutes. How often the scheduler fetches fresh metrics.</div>
		</div>
		{#if settingsError}
			<div class="text-red-400 text-sm">{settingsError}</div>
		{/if}
		<div class="flex justify-end gap-2">
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
