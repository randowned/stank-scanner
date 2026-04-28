<script lang="ts">
	import { base } from '$app/paths';
	import type { ChainSummary, ChainMessageEntry } from '$lib/types';
	import { formatDateTime } from '$lib/datetime';
	import { formatDuration } from '$lib/format';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import LeaderboardRow from '$lib/components/LeaderboardRow.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import Avatar from '$lib/components/Avatar.svelte';

	let { data } = $props();

	const chain = $derived(data.chain as ChainSummary | null);
	const names = $derived((data.names as Record<string, string> | undefined) ?? {});
	const timeline = $derived((chain?.timeline as ChainMessageEntry[] | undefined) ?? []);

	const classification = $derived(chain ? (chain.length < 5 ? 'Short' : chain.length < 20 ? 'Medium' : chain.length < 50 ? 'Long' : 'Epic') : '');
	const isAlive = $derived(!chain?.broken_at);
	const isRolledOver = $derived(!!chain?.rolled_over);

</script>

<div class="p-4 space-y-4">
	{#if chain}
		<!-- Status banner -->
		<div class="rounded-lg overflow-hidden">
			{#if isAlive}
				<div class="flex items-center gap-2 px-4 py-2 bg-ok/10">
					<span class="w-2.5 h-2.5 rounded-full bg-ok animate-pulse shrink-0" aria-hidden="true"></span>
					<span class="font-semibold text-ok text-sm">Chain is alive</span>
					<span class="text-xs text-muted ml-auto">{classification}</span>
				</div>
			{:else if isRolledOver}
				<div class="flex items-center gap-2 px-4 py-2 bg-accent/10">
					<span class="font-semibold text-accent text-sm">Rolled over</span>
					<span class="text-xs text-muted ml-auto">{classification}</span>
				</div>
			{:else}
				<div class="flex items-center gap-2 px-4 py-2 bg-danger/10">
					<span class="font-semibold text-danger text-sm">Chain broken</span>
					<span class="text-xs text-muted ml-auto">{classification}</span>
				</div>
			{/if}
		</div>

		<PageHeader title="⛓️ Chain #{chain.chain_id}" subtitle={chain.session_id ? `Session #${chain.session_id} · ${chain.altar_name ?? ''}` : ''} />

		<!-- Stat panel -->
		<div class="panel">
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
				<StatTile value={String(chain.length)} label="Length" color="text-accent" testId="chain-length" />
				<StatTile value={String(chain.unique_contributors)} label="Unique" color="text-text" testId="chain-unique" />
				{#if chain.total_reactions !== undefined}
					<StatTile value={String(chain.total_reactions)} label="Reactions" color="text-accent" testId="chain-reactions" />
				{/if}
				<StatTile value={formatDuration(chain.started_at, chain.broken_at)} label="Duration" color="text-text" testId="chain-duration" />
			</div>
			<div class="mt-2 pt-2 border-t border-border flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
				<span>Started: {formatDateTime(chain.started_at)}</span>
				<span>Ended: {formatDateTime(chain.broken_at, 'alive')}</span>
			</div>
		</div>

		<!-- Timeline -->
		{#if timeline.length > 0}
			<div class="panel" data-testid="chain-timeline">
				<h2 class="text-lg font-semibold mb-3">Chain Timeline</h2>
				<div class="space-y-1">
					{#each timeline as entry, i (entry.position)}
						{@const isStarter = i === 0}
						{@const isBreaker = chain.broken_at && i === timeline.length - 1}
						{@const thisIsBreaker = isBreaker || (chain.broken_at && String(entry.user_id) === String(chain.broken_by_user_id))}
						<div
							class="flex items-center gap-3 px-2 py-2 rounded-md {thisIsBreaker ? 'bg-danger/5' : isStarter ? 'bg-accent/5' : ''}"
							data-testid="timeline-row"
						>
							<span class="font-mono text-xs text-muted w-6 shrink-0 text-right">#{entry.position}</span>
							<Avatar name={entry.display_name} userId={entry.user_id} discordAvatar={entry.discord_avatar} size="sm" />
							<div class="flex-1 min-w-0 truncate text-sm">
								{entry.display_name}
								{#if isStarter}
									<span class="text-xs text-accent ml-1">Starter</span>
								{/if}
								{#if thisIsBreaker && chain.broken_at}
									<span class="text-xs text-danger ml-1">Breaker</span>
								{/if}
							</div>
							<div class="shrink-0 text-sm font-semibold tabular-nums {thisIsBreaker ? 'text-danger' : 'text-accent'}">
								{thisIsBreaker ? `-${Math.abs(entry.sp_awarded)}` : `+${entry.sp_awarded}`} SP
							</div>
						</div>
						{#if thisIsBreaker && chain.broken_at}
							<div class="flex items-center gap-2 px-2 py-1">
								<div class="h-px flex-1 bg-border/50"></div>
								<span class="text-xs text-muted italic">Chain broken</span>
								<div class="h-px flex-1 bg-border/50"></div>
							</div>
						{/if}
					{/each}
				</div>
			</div>
		{/if}

		<!-- Leaderboard -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Leaderboard</h2>
			{#if chain.leaderboard && chain.leaderboard.length}
				<div class="space-y-2">
					{#each chain.leaderboard as row, i}
						<LeaderboardRow rank={i + 1} {row} context="chain" />
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
						<LeaderboardRow rank={i + 1} row={fakeRow} context="chain" />
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