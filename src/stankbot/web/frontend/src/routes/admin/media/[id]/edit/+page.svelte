<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { apiFetch, apiPost, apiDelete } from '$lib/api';
	import { toErrorMessage } from '$lib/api-utils';
	import { formatNumber, formatRelativeTime, formatFreshness } from '$lib/format';
	import type { MediaItem } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	const mediaId = $derived(Number(($page.params as { id: string }).id));

	let item = $state<MediaItem | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let refreshing = $state(false);
	let refreshError = $state<string | null>(null);
	let deleteOpen = $state(false);

	async function loadItem() {
		loading = true;
		error = null;
		try {
			item = await apiFetch<MediaItem>(`/api/admin/media/${mediaId}`);
		} catch (err) {
			error = toErrorMessage(err, 'Failed to load');
		} finally {
			loading = false;
		}
	}

	async function handleRefresh() {
		refreshing = true;
		refreshError = null;
		try {
			await apiPost(`/api/admin/media/${mediaId}/refresh`);
			await loadItem();
		} catch (err) {
			refreshError = toErrorMessage(err, 'Refresh failed');
		} finally {
			refreshing = false;
		}
	}

	async function handleDelete() {
		try {
			await apiDelete(`/api/admin/media/${mediaId}`);
			goto(`${base}/admin/media`);
		} catch (err) {
			error = toErrorMessage(err, 'Failed to delete');
			deleteOpen = false;
		}
	}

	function metricValue(key: string): number {
		return (item?.metrics as Record<string, { value: number }>)?.[key]?.value ?? 0;
	}

	const freshness = $derived(formatFreshness(item?.metrics_last_fetched_at, 10));

	$effect(() => {
		loadItem();
	});
</script>

<div class="mb-4">
	<a href="{base}/admin/media" class="text-sm text-muted hover:text-accent transition-colors">← Back to Media</a>
</div>

{#if loading}
	<div class="panel animate-pulse space-y-3">
		<div class="h-6 bg-border rounded w-64"></div>
		<div class="h-4 bg-border rounded w-48"></div>
		<div class="grid grid-cols-3 gap-3">
			<div class="h-16 bg-border rounded"></div>
			<div class="h-16 bg-border rounded"></div>
			<div class="h-16 bg-border rounded"></div>
		</div>
	</div>
{:else if error}
	<div class="panel border-red-500/50">
		<div class="text-red-400">{error}</div>
	</div>
{:else if !item}
	<EmptyState icon="🎬" title="Not found" message="This media item could not be found." />
{:else}
	<PageHeader title={`Edit: ${item.title}`} subtitle={item.channel_name ?? 'Unknown channel'}>
		{#snippet actions()}
			<Button variant="secondary" onclick={handleRefresh} loading={refreshing} testId="media-edit-refresh">
				Force refresh
			</Button>
			<Button variant="ghost" onclick={() => (deleteOpen = true)} testId="media-edit-delete">
				Delete
			</Button>
		{/snippet}
	</PageHeader>

	<div class="panel space-y-4">
		{#if refreshError}
			<div class="text-red-400 text-sm">{refreshError}</div>
		{/if}

		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			<div class="md:col-span-1">
				{#if item.thumbnail_url}
					<img src={item.thumbnail_url} alt={item.title} class="w-full rounded-lg" loading="lazy" />
				{:else}
					<div class="w-full aspect-video bg-border rounded-lg flex items-center justify-center text-5xl text-muted">▶️</div>
				{/if}
				<div class="mt-3 text-sm space-y-1">
					<div class="text-muted">Type: <span class="text-text capitalize">{item.media_type}</span></div>
				<div class="text-muted">External ID: <span class="text-text text-xs font-mono">{item.external_id}</span></div>
				<div class="text-muted">Slug: <span class="text-text font-mono">{item.slug ?? '—'}</span></div>
				<div class="text-muted">Added by: <span class="text-text">{item.added_by}</span></div>
					<div class="text-muted">Published: <span class="text-text">{item.published_at ? formatRelativeTime(item.published_at) : '—'}</span></div>
					<div class="{freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}">
						Metrics: <span>{freshness.label}</span>
					</div>
				</div>
			</div>

			<div class="md:col-span-2">
				<div class="grid grid-cols-3 gap-3">
					<StatTile
						value={formatNumber(metricValue('view_count'))}
						label="Views"
						testId="media-edit-views"
						valueTestId="media-edit-views-value"
					/>
					<StatTile
						value={formatNumber(metricValue('like_count'))}
						label="Likes"
						testId="media-edit-likes"
						valueTestId="media-edit-likes-value"
					/>
					<StatTile
						value={formatNumber(metricValue('comment_count'))}
						label="Comments"
						testId="media-edit-comments"
						valueTestId="media-edit-comments-value"
					/>
				</div>
			</div>
		</div>
	</div>

	<ConfirmDialog
		bind:open={deleteOpen}
		title="Delete media?"
		body="Delete &quot;{item.title}&quot;? This also removes all cached metrics and history."
		confirmLabel="Delete"
		danger={true}
		onconfirm={handleDelete}
	/>
{/if}
