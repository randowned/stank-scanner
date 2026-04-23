<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { apiFetch, FetchError } from '$lib/api';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import type { GuildInfo, BoardState } from '$lib/types';

	const guilds = $derived(($page.data.guilds as GuildInfo[] | undefined) ?? []);
	const missingBot = $derived(guilds.filter((g) => g.is_admin && !g.bot_present));

	const tiles = [
		{ href: `${base}/admin/settings`, label: 'Settings', icon: '⚙️', desc: 'Altar, scoring, session ops' },
		{ href: `${base}/admin/templates`, label: 'Templates', icon: '📝', desc: 'Edit bot embeds' },
		{ href: `${base}/admin/admins`, label: 'Admins', icon: '👥', desc: 'Admin role & user grants' },
		{ href: `${base}/admin/audit`, label: 'Audit log', icon: '📋', desc: 'History of admin actions' }
	];

	let board = $state<BoardState | null>(null);

	onMount(async () => {
		try {
			board = await apiFetch<BoardState>('/api/board');
		} catch (err) {
			if (!(err instanceof FetchError)) throw err;
		}
	});

	function formatNextReset(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return (
			d.toLocaleString('en-US', {
				month: 'short',
				day: 'numeric',
				hour: 'numeric',
				minute: '2-digit',
				timeZone: 'UTC'
			}) + ' UTC'
		);
	}
</script>

<PageHeader title="Admin" subtitle="Per-guild configuration and operations" />

{#if board}
	<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
		<div class="panel text-center">
			<div class="text-xl font-bold text-accent">{board.current}</div>
			<div class="text-xs text-muted uppercase">Current chain</div>
		</div>
		<div class="panel text-center">
			<div class="text-xl font-bold">{board.record}</div>
			<div class="text-xs text-muted uppercase">Session record</div>
		</div>
		<div class="panel text-center">
			<div class="text-xl font-bold">{board.alltime_record}</div>
			<div class="text-xs text-muted uppercase">All-time</div>
		</div>
		<div class="panel text-center">
			<div class="text-sm font-semibold">{formatNextReset(board.next_reset_at)}</div>
			<div class="text-xs text-muted uppercase">Next reset</div>
		</div>
	</div>
{/if}

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
	{#each tiles as tile (tile.href)}
		<a href={tile.href} class="panel hover:border-accent transition-colors block">
			<div class="flex items-start gap-3">
				<div class="text-2xl" aria-hidden="true">{tile.icon}</div>
				<div class="min-w-0">
					<div class="font-semibold truncate">{tile.label}</div>
					<div class="text-xs text-muted">{tile.desc}</div>
				</div>
			</div>
		</a>
	{/each}
</div>

{#if missingBot.length > 0}
	<section class="mt-6">
		<Card title="Invite the bot to your other guilds">
			<ul class="divide-y divide-border -mb-4 -mx-4">
				{#each missingBot as g (g.id)}
					<li class="flex items-center justify-between px-4 py-2">
						<div class="flex items-center gap-3 min-w-0">
							{#if g.icon_url}
								<img src={g.icon_url} alt="" class="w-8 h-8 rounded-full" />
							{:else}
								<div class="w-8 h-8 rounded-full bg-border flex items-center justify-center text-xs">
									{g.name[0] ?? '?'}
								</div>
							{/if}
							<div class="truncate">{g.name}</div>
						</div>
						<a href="/auth/login?install_guild={g.id}" class="text-sm text-accent hover:underline"
							>Add bot</a
						>
					</li>
				{/each}
			</ul>
		</Card>
	</section>
{/if}
