<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { apiFetch, apiPost, apiDelete } from '$lib/api';
	import { toErrorMessage } from '$lib/api-utils';
	import { formatFreshness, formatRelativeTime } from '$lib/format';
	import { formatIsoLocal } from '$lib/datetime';
	import type { MediaItem, MetricDef } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import Tabs from '$lib/components/Tabs.svelte';

	const mediaId = $derived(Number(($page.params as { id: string }).id));

	let item = $state<MediaItem | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let refreshing = $state(false);
	let refreshError = $state<string | null>(null);
	let deleteOpen = $state(false);

	let nameValue = $state('');
	let nameSaving = $state(false);
	let nameError = $state<string | null>(null);
	let nameSaved = $state(false);

	let snapshots = $state<Array<Record<string, string | number>>>([]);
	let metricDefs = $state<MetricDef[]>([]);
	let loadingSnapshots = $state(false);

	let ownerSnapshots = $state<Array<Record<string, string | number>>>([]);
	let ownerMetricDefs = $state<MetricDef[]>([]);
	let loadingOwnerSnapshots = $state(false);

	let snapshotTab = $state<'media' | 'owner'>('media');

	const freshness = $derived(formatFreshness(item?.metrics_last_fetched_at, 10));

	const ownerTabLabel = $derived(
		item?.media_type === 'spotify' ? 'Artist Snapshots' : 'Channel Snapshots'
	);

	async function loadItem() {
		loading = true;
		error = null;
		try {
			item = await apiFetch<MediaItem>(`/api/admin/media/${mediaId}`);
			nameValue = item.name ?? '';
		} catch (err) {
			error = toErrorMessage(err, 'Failed to load');
		} finally {
			loading = false;
		}
	}

	async function loadSnapshots() {
		loadingSnapshots = true;
		try {
			const res = await apiFetch<{ snapshots: Array<Record<string, string | number>>; metric_defs: MetricDef[] }>(
				`/api/admin/media/${mediaId}/snapshots?limit=20`
			);
			snapshots = res.snapshots;
			metricDefs = res.metric_defs;
		} catch {
			snapshots = [];
		} finally {
			loadingSnapshots = false;
		}
	}

	async function loadOwnerSnapshots() {
		loadingOwnerSnapshots = true;
		try {
			const res = await apiFetch<{ snapshots: Array<Record<string, string | number>>; metric_defs: MetricDef[] }>(
				`/api/admin/media/${mediaId}/owner/history?limit=20`
			);
			ownerSnapshots = res.snapshots;
			ownerMetricDefs = res.metric_defs;
		} catch {
			ownerSnapshots = [];
		} finally {
			loadingOwnerSnapshots = false;
		}
	}

	async function saveName() {
		nameSaving = true;
		nameError = null;
		nameSaved = false;
		try {
			const res = await fetch(`/api/admin/media/${mediaId}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: nameValue || null }),
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Failed to save' }));
				throw new Error(err.detail || 'Failed to save');
			}
			await loadItem();
			nameSaved = true;
			setTimeout(() => (nameSaved = false), 2000);
		} catch (err) {
			nameError = toErrorMessage(err, 'Failed to save name');
		} finally {
			nameSaving = false;
		}
	}

	async function handleRefresh() {
		refreshing = true;
		refreshError = null;
		try {
			await apiPost(`/api/admin/media/${mediaId}/refresh`);
			await loadItem();
			await loadSnapshots();
			await loadOwnerSnapshots();
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

	function formatCellValue(key: string, val: number | string): string {
		if (typeof val === 'string') return val;
		const def = metricDefs.find((m) => m.key === key);
		if (def?.format === 'percentage') return `${Math.round(val)}%`;
		return val.toLocaleString('en-US');
	}

	function formatOwnerCellValue(key: string, val: number | string): string {
		if (typeof val === 'string') return val;
		const def = ownerMetricDefs.find((m) => m.key === key);
		if (def?.format === 'percentage') return `${Math.round(val)}%`;
		return val.toLocaleString('en-US');
	}

	const columnKeys = $derived(metricDefs.map((m) => m.key));
	const ownerColumnKeys = $derived(ownerMetricDefs.map((m) => m.key));

	$effect(() => {
		loadItem();
		loadSnapshots();
	});
</script>

<div class="mb-4">
	<a href="{base}/admin/media" class="text-sm text-muted hover:text-accent transition-colors">← Back to Media</a>
</div>

{#if loading}
	<div class="panel animate-pulse space-y-3">
		<div class="h-6 bg-border rounded w-64"></div>
		<div class="h-4 bg-border rounded w-48"></div>
		<div class="h-4 bg-border rounded w-32"></div>
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

	<div class="space-y-4">
		{#if refreshError}
			<div class="text-red-400 text-sm">{refreshError}</div>
		{/if}

		<!-- Name editor -->
		<div class="panel">
			<div class="flex flex-col sm:flex-row sm:items-center gap-3">
				<div class="flex-1 min-w-0">
					<label for="media-name" class="block text-xs text-muted mb-1">Name</label>
					<div class="flex gap-2">
						<input
							id="media-name"
							type="text"
							bind:value={nameValue}
							class="flex-1 px-3 py-1.5 text-sm rounded border border-border bg-panel text-text placeholder:text-muted focus:outline-none focus:border-accent"
							placeholder="e.g. my-track"
							maxlength={64}
							disabled={nameSaving}
							data-testid="media-edit-name"
						/>
						<Button
							variant="primary"
							onclick={saveName}
							loading={nameSaving}
							disabled={nameSaving}
							testId="media-edit-save-name"
							size="sm"
						>
							Save
						</Button>
					</div>
					{#if nameError}
						<div class="text-red-400 text-xs mt-1">{nameError}</div>
					{/if}
					{#if nameSaved}
						<div class="text-green-400 text-xs mt-1">Name saved</div>
					{/if}
				</div>
				<div class="text-xs text-muted sm:text-right shrink-0 space-y-0.5">
					<div>Type: <span class="text-text capitalize">{item.media_type}</span></div>
					<div>External ID: <span class="text-text font-mono">{item.external_id}</span></div>
				</div>
			</div>
		</div>

		<!-- Metadata -->
		<div class="panel">
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
				<div class="text-muted">Added by: <span class="text-text">{item.added_by}</span></div>
				<div class="text-muted">Published: <span class="text-text">{item.published_at ? formatRelativeTime(item.published_at) : '\u2014'}</span></div>
				<div class="{freshness.state === 'stale' ? 'text-amber-500' : freshness.state === 'dead' ? 'text-red-500' : 'text-muted'}">
					Metrics last updated: <span>{freshness.label}</span>
				</div>
			</div>
		</div>

		<!-- Debug info (thumbnail)-->
		{#if item.thumbnail_url}
			<div class="panel"><img src={item.thumbnail_url} alt="" class="w-32 rounded" loading="lazy" /></div>
		{/if}

		<!-- Snapshots tabs -->
		<div class="panel overflow-hidden">
			<Tabs
				tabs={[
					{ value: 'media' as const, label: 'Media Snapshots' },
					{ value: 'owner' as const, label: ownerTabLabel },
				]}
				bind:value={snapshotTab}
			/>

			{#if snapshotTab === 'media'}
				{#if loadingSnapshots}
					<div class="space-y-1">
						{#each Array(5) as _}
							<div class="h-4 bg-border rounded animate-pulse w-full"></div>
						{/each}
					</div>
				{:else if snapshots.length === 0}
					<div class="text-muted text-sm py-4 text-center">No snapshots yet. Force refresh to pull the first metrics.</div>
				{:else}
					<div class="overflow-x-auto -mx-4 sm:-mx-0">
						<table class="w-full text-xs" data-testid="media-edit-snapshots">
							<thead>
								<tr class="border-b border-border">
									<th class="text-left text-muted font-medium py-2 px-2 sm:px-3 whitespace-nowrap">Time</th>
									{#each columnKeys as key}
										<th class="text-right text-muted font-medium py-2 px-2 sm:px-3 whitespace-nowrap">
											{metricDefs.find((d) => d.key === key)?.label ?? key}
										</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each snapshots as row, i}
									<tr class="border-b border-border last:border-0 {i % 2 === 1 ? 'bg-panel/30' : ''}">
										<td class="py-1.5 px-2 sm:px-3 text-muted whitespace-nowrap font-mono tabular-nums">
											{formatIsoLocal(row.fetched_at as string)}
										</td>
										{#each columnKeys as key}
											<td class="py-1.5 px-2 sm:px-3 text-right text-text whitespace-nowrap tabular-nums">
												{formatCellValue(key, row[key] ?? 0)}
											</td>
										{/each}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{:else}
				{#if loadingOwnerSnapshots}
					<div class="space-y-1">
						{#each Array(5) as _}
							<div class="h-4 bg-border rounded animate-pulse w-full"></div>
						{/each}
					</div>
				{:else if ownerSnapshots.length === 0}
					<div class="text-muted text-sm py-4 text-center" data-testid="owner-snapshots-empty">
						No {item.media_type === 'spotify' ? 'artist' : 'channel'} snapshots yet. Force refresh to pull the first data.
					</div>
				{:else}
					<div class="overflow-x-auto -mx-4 sm:-mx-0">
						<table class="w-full text-xs" data-testid="media-edit-owner-snapshots">
							<thead>
								<tr class="border-b border-border">
									<th class="text-left text-muted font-medium py-2 px-2 sm:px-3 whitespace-nowrap">Time</th>
									{#each ownerColumnKeys as key}
										<th class="text-right text-muted font-medium py-2 px-2 sm:px-3 whitespace-nowrap">
											{ownerMetricDefs.find((d) => d.key === key)?.label ?? key}
										</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each ownerSnapshots as row, i}
									<tr class="border-b border-border last:border-0 {i % 2 === 1 ? 'bg-panel/30' : ''}">
										<td class="py-1.5 px-2 sm:px-3 text-muted whitespace-nowrap font-mono tabular-nums">
											{formatIsoLocal(row.fetched_at as string)}
										</td>
										{#each ownerColumnKeys as key}
											<td class="py-1.5 px-2 sm:px-3 text-right text-text whitespace-nowrap tabular-nums">
												{formatOwnerCellValue(key, row[key] ?? 0)}
											</td>
										{/each}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{/if}
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
