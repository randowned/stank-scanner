<script lang="ts">
	import { base } from '$app/paths';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import { BOT_INVITE_URL } from '$lib/config';

	const inviteUrl = BOT_INVITE_URL;

	const tiles = [
		{ href: `${base}/admin/channels`, label: 'Channels', icon: '📡', desc: 'Altar and announcement channels' },
		{ href: `${base}/admin/templates`, label: 'Templates', icon: '📝', desc: 'Edit bot embed templates' },
		{ href: `${base}/admin/media`, label: 'Media', icon: '🎬', desc: 'YouTube & Spotify metrics tracking' },
		{ href: `${base}/admin/admins`, label: 'Admins', icon: '👥', desc: 'Admin role & user grants' },
		{ href: `${base}/admin/audit`, label: 'Audit log', icon: '📋', desc: 'History of admin actions' },
		{ href: `${base}/admin/events`, label: 'Events', icon: '📜', desc: 'Game event log (stanks, breaks, reactions)' },
		{ href: `${base}/admin/sessions`, label: 'Sessions', icon: '🔄', desc: 'Start, rebuild, or reset sessions' },
		{ href: `${base}/admin/settings`, label: 'Settings', icon: '⚙️', desc: 'Scoring, behavior, and resets' }
	];

	let copied = $state(false);

	async function copyInvite() {
		if (!inviteUrl) return;
		await navigator.clipboard.writeText(inviteUrl);
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}
</script>

<PageHeader title="Admin" subtitle="Per-guild configuration and operations" />

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

{#if inviteUrl}
	<div class="panel mt-4 flex items-center justify-between gap-3">
		<div class="min-w-0">
			<div class="font-medium text-sm">Bot invite link</div>
			<div class="text-xs text-muted truncate">{inviteUrl}</div>
		</div>
		<button
			onclick={copyInvite}
			class="shrink-0 text-sm px-3 py-1.5 rounded-md border border-border hover:border-accent transition-colors {copied ? 'text-ok' : 'text-accent'}"
		>
			{copied ? '✓ Copied' : 'Copy link'}
		</button>
	</div>
{/if}
