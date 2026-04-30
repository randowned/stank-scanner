<script lang="ts">
	import { base } from '$app/paths';
	import { formatDateTime } from '$lib/datetime';
	import Duration from '$lib/components/Duration.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Avatar from '$lib/components/Avatar.svelte';

	let { data } = $props();

	const session = $derived(data.session);
	const names = $derived((data.names as Record<string, string>) ?? {});

	function playerName(userId: string): string {
		return names[userId] ?? `#${userId}`;
	}

</script>

<div class="p-4 space-y-4">
	{#if session}
		<PageHeader title="Session #{session.session_id}" subtitle={formatDateTime(session.started_at)} />

		<Card title="Summary">
			<dl class="grid grid-cols-2 gap-4 text-sm">
				<div>
					<dt class="text-muted uppercase text-xs">Started</dt>
					<dd>{formatDateTime(session.started_at)}</dd>
				</div>
				<div>
					<dt class="text-muted uppercase text-xs">Ended</dt>
					<dd>{formatDateTime(session.ended_at)}</dd>
				</div>
				<div>
					<dt class="text-muted uppercase text-xs">Chains started</dt>
					<dd class="text-lg font-bold">{session.chains_started}</dd>
				</div>
				<div>
					<dt class="text-muted uppercase text-xs">Chains broken</dt>
					<dd class="text-lg font-bold">{session.chains_broken}</dd>
				</div>
				{#if session.total_stanks !== undefined}
				<div>
					<dt class="text-muted uppercase text-xs">Total stanks</dt>
					<dd class="text-lg font-bold">{session.total_stanks}</dd>
				</div>
				{/if}
				{#if session.total_reactions !== undefined}
				<div>
					<dt class="text-muted uppercase text-xs">Total reactions</dt>
					<dd class="text-lg font-bold">{session.total_reactions}</dd>
				</div>
				{/if}
				{#if session.total_sp !== undefined}
				<div>
					<dt class="text-muted uppercase text-xs">Total SP</dt>
					<dd class="text-lg font-bold text-accent">{session.total_sp}</dd>
				</div>
				{/if}
				{#if session.total_pp !== undefined}
				<div>
					<dt class="text-muted uppercase text-xs">Total PP</dt>
					<dd class="text-lg font-bold text-danger">{session.total_pp}</dd>
				</div>
				{/if}
			</dl>
			<div class="mt-2 pt-2 border-t border-border text-xs text-muted">
				Duration: <Duration start={session.started_at} end={session.ended_at} />
			</div>
		</Card>

		<!-- Session Leaderboard -->
		{#if session.session_leaderboard && session.session_leaderboard.length > 0}
			<Card title="Session Leaderboard">
				<div class="space-y-1">
					{#each session.session_leaderboard.slice(0, 5) as entry, i}
						<a
							href="{base}/player/{entry.user_id}"
							class="flex items-center gap-3 px-2 py-2 rounded-md hover:bg-border/40 text-sm"
						>
							<span class="font-mono text-xs text-muted w-5 shrink-0">#{i + 1}</span>
							<Avatar name={entry.display_name} userId={entry.user_id} discordAvatar={entry.discord_avatar} size="sm" />
							<span class="flex-1 min-w-0 truncate">{entry.display_name}</span>
							<span class="shrink-0 font-semibold tabular-nums text-accent">+{entry.net}</span>
						</a>
					{/each}
				</div>
				{#snippet footer()}
					<div class="flex justify-between text-xs text-muted">
						<span>Top earner: {session.top_earner ? `${playerName(session.top_earner[0])} (${session.top_earner[1]} SP)` : '—'}</span>
						<span>Top breaker: {session.top_breaker ? `${playerName(session.top_breaker[0])} (${session.top_breaker[1]} PP)` : '—'}</span>
					</div>
				{/snippet}
			</Card>
		{:else}
			{#if session.top_earner}
				<Card title="Top earner">
					<a
						href="{base}/player/{session.top_earner[0]}"
						class="flex items-center justify-between hover:bg-border/40 -m-2 p-2 rounded-md"
					>
						<span class="font-medium text-sm">{playerName(session.top_earner[0])}</span>
						<span class="font-bold text-accent">{session.top_earner[1]} SP</span>
					</a>
				</Card>
			{/if}
			{#if session.top_breaker}
				<Card title="Top chainbreaker">
					<a
						href="{base}/player/{session.top_breaker[0]}"
						class="flex items-center justify-between hover:bg-border/40 -m-2 p-2 rounded-md"
					>
						<span class="font-medium text-sm">{playerName(session.top_breaker[0])}</span>
						<span class="font-bold text-danger">-{session.top_breaker[1]} SP</span>
					</a>
				</Card>
			{/if}
		{/if}

		{#if session.chains && session.chains.length > 0}
		<Card title="Chains ({session.chains.length})">
			<ul class="space-y-1">
				{#each session.chains as c (c.chain_id)}
					{@const rolledOver = !!session.ended_at && (!c.broken_at || new Date(c.broken_at) > new Date(session.ended_at))}
					<a
						href="{base}/chain/{c.chain_id}"
						class="flex items-center justify-between gap-3 px-2 py-3 rounded-md hover:bg-border/40 text-sm"
					>
						<span class="font-mono text-muted shrink-0">#{c.chain_id}</span>
						<span class="flex-1 min-w-0 truncate">{formatDateTime(c.started_at)}</span>
						<span class="shrink-0 tabular-nums">
							{c.length}
							<span class="text-muted text-xs">/ {c.unique_contributors}</span>
						</span>
						<span class="shrink-0 text-xs font-semibold {rolledOver ? 'text-accent' : c.broken_at ? 'text-danger' : 'text-ok'}">
							{rolledOver ? 'ROLLOVER' : c.broken_at ? 'BROKEN' : 'OPEN'}
						</span>
					</a>
				{/each}
			</ul>
		</Card>
	{:else}
		<Card title="Chains">
			<EmptyState icon="🔗" title="No chains in this session yet" />
		</Card>
	{/if}

	<a href="{base}/sessions" class="btn btn-secondary w-full text-center">← All sessions</a>
	{:else}
		<EmptyState icon="📜" title="Session not found" />
	{/if}
</div>