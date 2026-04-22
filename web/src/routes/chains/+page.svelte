<script lang="ts">
	import { base } from '$app/paths';
	import type { ChainSummary } from '../../app.d';

	let { data } = $props();

	const chains = $derived(data.chains as ChainSummary[]);

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return 'alive';
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
	<div class="panel">
		<h1 class="text-xl font-bold flex items-center gap-2">
			<span>⛓️</span>
			<span>Chain History</span>
		</h1>
	</div>

	{#if !chains.length}
		<div class="panel">
			<p class="text-muted text-center py-8">No chains recorded yet.</p>
		</div>
	{:else}
		<div class="space-y-2">
			{#each chains as chain}
				<a href="{base}/chain/{chain.chain_id}" class="panel flex items-center justify-between">
					<div>
						<div class="font-medium">#{chain.chain_id}</div>
						<div class="text-xs text-muted">
							{formatDate(chain.started_at)} · {chain.unique_contributors} unique
						</div>
					</div>
					<div class="text-right">
						<div class="text-xl font-bold text-accent">{chain.length}</div>
						<div class="text-xs text-muted uppercase">stanks</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}

	<a href={base} class="btn btn-secondary w-full text-center">← Back to Board</a>
</div>