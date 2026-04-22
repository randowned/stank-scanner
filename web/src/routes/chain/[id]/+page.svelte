<script lang="ts">
	import { base } from '$app/paths';
	import type { ChainSummary } from '../../../app.d';

	let { data } = $props();

	const chain = $derived(data.chain as ChainSummary | null);

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

	function getPlayerUrl(userId: number): string {
		return `${base}/player/${userId}`;
	}
</script>

<div class="p-4 space-y-4">
	{#if chain}
		<div class="panel">
			<h1 class="text-xl font-bold flex items-center gap-2">
				<span>⛓️</span>
				<span>Chain #{chain.chain_id}</span>
			</h1>
		</div>

		<div class="panel">
			<div class="grid grid-cols-2 gap-3">
				<div>
					<div class="text-xl font-bold text-accent">{chain.length}</div>
					<div class="text-xs text-muted uppercase">Length</div>
				</div>
				<div>
					<div class="text-xl font-bold">{chain.unique_contributors}</div>
					<div class="text-xs text-muted uppercase">Unique</div>
				</div>
				<div>
					<div class="text-sm text-muted">Started</div>
					<div class="text-sm">{formatDate(chain.started_at)}</div>
				</div>
				<div>
					<div class="text-sm text-muted">Ended</div>
					<div class="text-sm">{formatDate(chain.broken_at)}</div>
				</div>
			</div>
		</div>

		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Contributors</h2>
			{#if chain.contributors.length}
				<div class="space-y-2">
					{#each chain.contributors as [userId, count], i}
						<a href={getPlayerUrl(userId)} class="flex items-center gap-3 p-2 -mx-2 rounded-lg hover:bg-border/50">
							<div class="w-6 h-6 flex items-center justify-center rounded-full bg-border text-sm">
								{i + 1}
							</div>
							<div class="flex-1">
								<div class="font-medium">Player #{userId}</div>
							</div>
							<div class="text-accent font-semibold">{count}</div>
						</a>
					{/each}
				</div>
			{:else}
				<p class="text-muted">No contributors.</p>
			{/if}
		</div>
	{:else}
		<div class="panel">
			<p class="text-muted">Chain not found.</p>
		</div>
	{/if}

	<a href="{base}/chains" class="btn btn-secondary w-full text-center">← All Chains</a>
</div>