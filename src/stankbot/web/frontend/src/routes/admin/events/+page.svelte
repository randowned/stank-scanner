<script lang="ts">
	import { apiFetch, FetchError } from '$lib/api';
	import { formatDateTime } from '$lib/datetime';
	import { onMount } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Input from '$lib/components/Input.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';

	interface Entry {
		id: number;
		created_at: string | null;
		type: string;
		user_id: string | null;
		user_name: string | null;
		delta: number;
		reason: string | null;
		chain_id: number | null;
		message_id: string | null;
	}

	const LIMIT = 100;

	let entries = $state<Entry[]>([]);
	let offset = $state(0);
	let loading = $state(false);
	let exhausted = $state(false);
	let error = $state<string | null>(null);
	let filterText = $state('');

	let sentinel: HTMLElement | undefined = $state();
	let observer: IntersectionObserver | undefined;

	function formatType(type: string): string {
		return type.replace(/_/g, ' ');
	}

	function typeBadgeClass(type: string): string {
		if (type.startsWith('sp_')) return 'badge-sp';
		if (type === 'pp_break') return 'badge-pp';
		if (type.startsWith('chain_') || type.startsWith('session_')) return 'badge-lifecycle';
		if (type === 'achievement_unlocked') return 'badge-achievement';
		return 'badge-other';
	}

	function deltaLabel(delta: number): string {
		if (delta === 0) return '';
		if (delta > 0) return `+${delta}`;
		return `${delta}`;
	}

	function deltaClass(delta: number): string {
		if (delta > 0) return 'delta-pos';
		if (delta < 0) return 'delta-neg';
		return '';
	}

	function loadPage(reset = false) {
		if (loading) return;
		if (!reset && exhausted) return;
		loading = true;
		error = null;
		if (reset) offset = 0;

		const params = new SvelteURLSearchParams({ limit: String(LIMIT), offset: String(offset) });
		if (filterText.trim()) params.set('q', filterText.trim());

		apiFetch<{ entries: Entry[] }>(`/api/admin/events?${params}`)
			.then((res) => {
				entries = reset ? res.entries : [...entries, ...res.entries];
				offset += res.entries.length;
				exhausted = res.entries.length < LIMIT;
			})
			.catch((err) => {
				error = err instanceof FetchError ? err.message : 'Failed to load events';
			})
			.finally(() => {
				loading = false;
			});
	}

	function onIntersect(entries_: IntersectionObserverEntry[]) {
		if (entries_[0]?.isIntersecting) {
			loadPage(false);
		}
	}

	$effect(() => {
		if (observer) observer.disconnect();
		if (!sentinel) return;
		observer = new IntersectionObserver(onIntersect, { rootMargin: '400px' });
		observer.observe(sentinel);
		return () => observer?.disconnect();
	});

	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		const _ = filterText;
		clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => loadPage(true), 300);
		return () => clearTimeout(debounceTimer);
	});

	onMount(() => loadPage(true));
</script>

<PageHeader title="Game events" subtitle="All stanks, breaks, reactions, achievements, and session events" />

<Card>
	<div class="flex flex-wrap gap-2 mb-3">
		<Input
			bind:value={filterText}
			placeholder="Search events… (grep across type, reason)"
		/>
	</div>

	{#if error && entries.length === 0}
		<ErrorState message={error} onretry={() => loadPage(true)} />
	{:else if entries.length === 0 && !loading}
		<EmptyState icon="📜" title="No events yet" message="Inject some stanks or breaks to see events here" />
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="text-left text-muted border-b border-border">
						<th class="py-2 pr-2">When</th>
						<th class="py-2 pr-2">Type</th>
						<th class="py-2 pr-2">User</th>
						<th class="py-2 pr-2 text-right">Points</th>
						<th class="py-2">Reason</th>
					</tr>
				</thead>
				<tbody>
					{#each entries as e (e.id)}
						<tr class="border-b border-border/60 align-top">
							<td class="py-2 pr-2 whitespace-nowrap text-muted text-xs">
								{formatDateTime(e.created_at, '')}
							</td>
							<td class="py-2 pr-2">
								<span class="badge {typeBadgeClass(e.type)}">{formatType(e.type)}</span>
							</td>
							<td class="py-2 pr-2">{e.user_name ?? e.user_id ?? '—'}</td>
							<td class="py-2 pr-2 text-right font-mono whitespace-nowrap">
								{#if e.delta !== 0}
									<span class={deltaClass(e.delta)}>{deltaLabel(e.delta)}</span>
								{:else}
									<span class="text-muted">—</span>
								{/if}
							</td>
							<td class="py-2 text-muted text-xs max-w-xs truncate">
								{e.reason ?? '—'}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div
			bind:this={sentinel}
			class="flex items-center justify-center py-4 text-sm text-muted"
		>
			{#if loading}
				<span>Loading…</span>
			{:else if exhausted && entries.length > 0}
				<span>All events loaded</span>
			{:else}
				<span>Scroll for more</span>
			{/if}
		</div>
	{/if}
</Card>

<style>
	.badge {
		display: inline-block;
		padding: 1px 7px;
		border-radius: 9999px;
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		white-space: nowrap;
	}
	.badge-sp {
		background: rgba(34, 197, 94, 0.15);
		color: #22c55e;
	}
	.badge-pp {
		background: rgba(239, 68, 68, 0.15);
		color: #ef4444;
	}
	.badge-lifecycle {
		background: rgba(59, 130, 246, 0.15);
		color: #3b82f6;
	}
	.badge-achievement {
		background: rgba(168, 85, 247, 0.15);
		color: #a855f7;
	}
	.badge-other {
		background: rgba(156, 163, 175, 0.15);
		color: #9ca3af;
	}
	.delta-pos {
		color: #22c55e;
	}
	.delta-neg {
		color: #ef4444;
	}
</style>
