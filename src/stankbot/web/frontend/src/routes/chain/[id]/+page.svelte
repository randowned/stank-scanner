<script lang="ts">
	import { base } from '$app/paths';
	import type { ChainSummary } from '$lib/types';
	import { formatDateTime } from '$lib/datetime';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import LeaderboardRow from '$lib/components/LeaderboardRow.svelte';

	let { data } = $props();

	const chain = $derived(data.chain as ChainSummary | null);
	const names = $derived((data.names as Record<string, string> | undefined) ?? {});
</script>

<div class="p-4 space-y-4">
	{#if chain}
		<PageHeader title="⛓️ Chain #{chain.chain_id}" subtitle={chain.broken_at ? 'Broken' : 'Alive'}>
			{#snippet actions()}
				{#if !chain.broken_at}
					<span
						class="w-2.5 h-2.5 rounded-full bg-ok animate-pulse"
						title="Chain is alive"
						aria-label="Chain is alive"
					></span>
				{/if}
			{/snippet}
		</PageHeader>

		<div class="panel">
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
				<div>
					<div class="text-xl font-bold text-accent">{chain.length}</div>
					<div class="text-xs text-muted uppercase">Length</div>
				</div>
				<div>
					<div class="text-xl font-bold">{chain.unique_contributors}</div>
					<div class="text-xs text-muted uppercase">Unique</div>
				</div>
				{#if chain.total_reactions !== undefined}
				<div>
					<div class="text-xl font-bold">{chain.total_reactions}</div>
					<div class="text-xs text-muted uppercase">Reactions</div>
				</div>
				{/if}
				<div>
					<div class="text-sm text-muted">Started</div>
					<div class="text-sm">{formatDateTime(chain.started_at)}</div>
				</div>
				<div>
					<div class="text-sm text-muted">Ended</div>
					<div class="text-sm">{formatDateTime(chain.broken_at, 'alive')}</div>
				</div>
			</div>
		</div>

		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Leaderboard</h2>
			{#if chain.leaderboard && chain.leaderboard.length}
				<div class="space-y-2">
					{#each chain.leaderboard as row, i}
						<LeaderboardRow rank={i + 1} {row} />
					{/each}
				</div>
			{:else if chain.contributors.length}
				<div class="space-y-2">
					{#each chain.contributors as [userId, count], i}
						{@const fakeRow = {
							user_id: userId,
							display_name: names[userId] ?? `#${userId}`,
							earned_sp: count,
							punishments: 0,
							net: count,
						}}
						<LeaderboardRow rank={i + 1} row={fakeRow} />
					{/each}
				</div>
			{:else}
				<EmptyState icon="👥" title="No contributors" message="This chain has no recorded contributors." />
			{/if}
		</div>
	{:else}
		<div class="panel">
			<EmptyState icon="❓" title="Chain not found" message="This chain doesn't exist or isn't visible to you." />
		</div>
	{/if}

	{#if chain?.session_id}
		<a href="{base}/session/{chain.session_id}" class="btn btn-secondary w-full text-center">← Session #{chain.session_id}</a>
	{/if}
</div>
