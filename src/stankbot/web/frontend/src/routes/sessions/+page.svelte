<script lang="ts">
	import { base } from '$app/paths';
	import type { SessionSummary } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';

	let { data } = $props();

	const sessions = $derived(data.sessions as SessionSummary[]);

	function formatDate(dateStr: string | null | undefined): string {
		if (!dateStr) return '—';
		return new Date(dateStr).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			timeZone: 'UTC'
		});
	}
</script>

<div class="p-4 space-y-4">
	<PageHeader title="📜 Session History" subtitle="Each entry is one reset window." />

	{#if !sessions.length}
		<div class="panel">
			<EmptyState icon="📜" title="No sessions yet" message="Completed sessions will appear here after the first reset." />
		</div>
	{:else}
		<div class="space-y-2">
			{#each sessions as s}
				<a href="{base}/session/{s.session_id}" class="panel block">
					<div class="flex items-center justify-between mb-1">
						<span class="font-medium">Session #{s.session_id}</span>
						{#if s.active}
							<span class="text-xs font-semibold text-ok">ACTIVE</span>
						{:else}
							<span class="text-xs font-semibold text-muted">ENDED</span>
						{/if}
					</div>
					<div class="text-xs text-muted mb-2">{formatDate(s.started_at)}</div>
					<div class="text-xs text-muted">
						Stankers: {s.unique_stankers ?? 0} · Stanks: {s.stanks ?? 0} · Chains: {s.chains ?? 0} · Reactions: {s.reactions ?? 0}
					</div>
				</a>
			{/each}
		</div>
	{/if}

	<a href="{base}/" class="btn btn-secondary w-full text-center">← Back to Board</a>
</div>
