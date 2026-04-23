<script lang="ts">
	import { base } from '$app/paths';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';

	let { data } = $props();

	const session = $derived(data.session);

	function fmt(s: string | null): string {
		if (!s) return '—';
		return new Date(s).toLocaleString();
	}
</script>

<div class="p-4 space-y-4">
	{#if session}
		<PageHeader title="Session #{session.session_id}" subtitle={fmt(session.started_at)} />

		<Card title="Summary">
			<dl class="grid grid-cols-2 gap-4 text-sm">
				<div>
					<dt class="text-muted uppercase text-xs">Started</dt>
					<dd>{fmt(session.started_at)}</dd>
				</div>
				<div>
					<dt class="text-muted uppercase text-xs">Ended</dt>
					<dd>{fmt(session.ended_at)}</dd>
				</div>
				<div>
					<dt class="text-muted uppercase text-xs">Chains started</dt>
					<dd class="text-lg font-bold">{session.chains_started}</dd>
				</div>
				<div>
					<dt class="text-muted uppercase text-xs">Chains broken</dt>
					<dd class="text-lg font-bold">{session.chains_broken}</dd>
				</div>
			</dl>
		</Card>

		{#if session.top_earner}
			<Card title="Top earner">
				<a
					href="{base}/player/{session.top_earner[0]}"
					class="flex items-center justify-between hover:bg-border/40 -m-2 p-2 rounded-md"
				>
					<span class="font-mono text-sm">#{session.top_earner[0]}</span>
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
					<span class="font-mono text-sm">#{session.top_breaker[0]}</span>
					<span class="font-bold text-danger">{session.top_breaker[1]}×</span>
				</a>
			</Card>
		{/if}

		{#if session.chains && session.chains.length > 0}
		<Card title="Chains ({session.chains.length})">
			<ul class="space-y-1">
				{#each session.chains as c (c.chain_id)}
					<a
						href="{base}/chain/{c.chain_id}"
						class="flex items-center justify-between gap-3 px-2 py-2 rounded-md hover:bg-border/40 text-sm"
					>
						<span class="font-mono text-muted shrink-0">#{c.chain_id}</span>
						<span class="flex-1 min-w-0 truncate">{fmt(c.started_at)}</span>
						<span class="shrink-0 tabular-nums">
							{c.length}
							<span class="text-muted text-xs">/ {c.unique_contributors}</span>
						</span>
						<span class="shrink-0 text-xs {c.broken_at ? 'text-danger' : 'text-ok'}">
							{c.broken_at ? 'broken' : 'open'}
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
