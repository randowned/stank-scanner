<script lang="ts">
	import { apiFetch, FetchError } from '$lib/api';
	import { onMount } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Input from '$lib/components/Input.svelte';
	import Button from '$lib/components/Button.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';

	interface Entry {
		id: number;
		created_at: string | null;
		actor_id: string | null;
		actor_name: string | null;
		action: string;
		payload: Record<string, unknown> | null;
	}

	let entries = $state<Entry[]>([]);
	let offset = $state(0);
	let loading = $state(false);
	let exhausted = $state(false);
	let error = $state<string | null>(null);

	let actionFilter = $state('');
	let actorFilter = $state('');

	async function loadPage(reset = false) {
		loading = true;
		error = null;
		try {
			if (reset) {
				offset = 0;
				entries = [];
				exhausted = false;
			}
			const params = new SvelteURLSearchParams({ limit: '50', offset: String(offset) });
			if (actionFilter.trim()) params.set('action', actionFilter.trim());
			if (actorFilter.trim()) params.set('actor_id', actorFilter.trim());
			const res = await apiFetch<{ entries: Entry[] }>(`/v2/api/admin/audit?${params}`);
			entries = reset ? res.entries : [...entries, ...res.entries];
			offset += res.entries.length;
			if (res.entries.length < 50) exhausted = true;
		} catch (err) {
			error = err instanceof FetchError ? err.message : 'Failed';
		} finally {
			loading = false;
		}
	}

	function fmtTime(s: string | null) {
		if (!s) return '';
		return new Date(s).toLocaleString();
	}

	type PayloadRow =
		| { kind: 'value'; key: string; value: string }
		| { kind: 'diff'; key: string; before: string; after: string };

	function fmtScalar(v: unknown): string {
		if (v === null || v === undefined) return '∅';
		if (typeof v === 'object') return JSON.stringify(v);
		return String(v);
	}

	function renderPayload(payload: Record<string, unknown>): PayloadRow[] {
		const out: PayloadRow[] = [];
		const before = payload.before as Record<string, unknown> | undefined;
		const after = payload.after as Record<string, unknown> | undefined;
		if (before && after && typeof before === 'object' && typeof after === 'object') {
			const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
			for (const k of keys) {
				const b = fmtScalar(before[k]);
				const a = fmtScalar(after[k]);
				if (b !== a) out.push({ kind: 'diff', key: k, before: b, after: a });
			}
			for (const [k, v] of Object.entries(payload)) {
				if (k === 'before' || k === 'after') continue;
				out.push({ kind: 'value', key: k, value: fmtScalar(v) });
			}
			return out;
		}
		for (const [k, v] of Object.entries(payload)) {
			out.push({ kind: 'value', key: k, value: fmtScalar(v) });
		}
		return out;
	}

	onMount(() => loadPage(true));
</script>

<PageHeader title="Audit log" subtitle="Recent admin actions on this guild" />

<Card>
	<div class="flex flex-wrap gap-2 mb-3">
		<Input bind:value={actionFilter} placeholder="Action (e.g. settings.update)" />
		<Input bind:value={actorFilter} type="number" placeholder="Actor ID" />
		<Button onclick={() => loadPage(true)}>Filter</Button>
	</div>

	{#if error}
		<ErrorState message={error} onretry={() => loadPage(true)} />
	{:else if entries.length === 0 && !loading}
		<EmptyState icon="📋" title="No audit entries" />
	{:else}
		<table class="w-full text-sm">
			<thead>
				<tr class="text-left text-muted border-b border-border">
					<th class="py-2 pr-2">When</th>
					<th class="py-2 pr-2">Actor</th>
					<th class="py-2 pr-2">Action</th>
					<th class="py-2">Payload</th>
				</tr>
			</thead>
			<tbody>
				{#each entries as e (e.id)}
					<tr class="border-b border-border/60 align-top">
						<td class="py-2 pr-2 whitespace-nowrap">{fmtTime(e.created_at)}</td>
						<td class="py-2 pr-2">{e.actor_name ?? e.actor_id ?? '—'}</td>
						<td class="py-2 pr-2 font-mono">{e.action}</td>
						<td class="py-2 text-xs break-all">
							{#if e.payload}
								{@const rows = renderPayload(e.payload)}
								{#if rows.length === 0}
									<span class="text-muted">—</span>
								{:else}
									<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
										{#each rows as row}
											<dt class="text-muted font-mono">{row.key}</dt>
											<dd>
												{#if row.kind === 'diff'}
													<span class="text-danger line-through mr-1">{row.before}</span>
													<span class="text-ok">{row.after}</span>
												{:else}
													<span class="text-text">{row.value}</span>
												{/if}
											</dd>
										{/each}
									</dl>
								{/if}
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>

		{#if !exhausted}
			<div class="mt-3 flex justify-center">
				<Button variant="secondary" onclick={() => loadPage(false)} loading={loading}>
					Load more
				</Button>
			</div>
		{/if}
	{/if}
</Card>
