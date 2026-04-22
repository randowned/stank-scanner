<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import type { PlayerProfile } from '../../../app.d';

	let { data } = $props();

	const profile = $derived(data.profile as PlayerProfile | null);
	const isLoading = $derived(!profile);
	const targetId = $derived(Number($page.params.id));

	function formatNumber(n: number): string {
		if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
		if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
		return n.toString();
	}

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '—';
		return new Date(dateStr).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			timeZone: 'UTC'
		}) + ' UTC';
	}
</script>

<div class="p-4 space-y-4">
	{#if isLoading}
		<div class="panel animate-pulse">
			<div class="h-6 bg-border rounded w-32 mb-4"></div>
			<div class="space-y-3">
				<div class="h-4 bg-border rounded w-24"></div>
				<div class="h-4 bg-border rounded w-24"></div>
			</div>
		</div>
	{:else if profile}
		<!-- Header -->
		<div class="panel">
			<h1 class="text-xl font-bold flex items-center gap-2">
				<span>📈</span>
				<span>{profile.display_name}</span>
			</h1>
			<p class="text-muted text-sm">Player #{targetId}</p>
		</div>

		<!-- Session Stats -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Session</h2>
			<div class="grid grid-cols-3 gap-3">
				<div>
					<div class="text-xl font-bold text-accent">{formatNumber(profile.session.earned_sp)}</div>
					<div class="text-xs text-muted uppercase">SP</div>
				</div>
				<div>
					<div class="text-xl font-bold text-danger">{formatNumber(profile.session.punishments)}</div>
					<div class="text-xs text-muted uppercase">PP</div>
				</div>
				<div>
					<div class="text-xl font-bold {profile.session.net >= 0 ? 'text-ok' : 'text-danger'}">{formatNumber(profile.session.net)}</div>
					<div class="text-xs text-muted uppercase">Net</div>
				</div>
			</div>
		</div>

		<!-- All-time Stats -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">All-time</h2>
			<div class="grid grid-cols-2 gap-3 mb-3">
				<div>
					<div class="text-xl font-bold text-accent">{formatNumber(profile.alltime.earned_sp)}</div>
					<div class="text-xs text-muted uppercase">SP</div>
				</div>
				<div>
					<div class="text-xl font-bold text-danger">{formatNumber(profile.alltime.punishments)}</div>
					<div class="text-xs text-muted uppercase">PP</div>
				</div>
				<div>
					<div class="text-xl font-bold">{profile.alltime.chains_started}</div>
					<div class="text-xs text-muted uppercase">Started</div>
				</div>
				<div>
					<div class="text-xl font-bold">{profile.alltime.chains_broken}</div>
					<div class="text-xs text-muted uppercase">Broken</div>
				</div>
			</div>

			{#if profile.last_stank_at}
				<div class="text-xs text-muted pt-3 border-t border-border">
					Last stank: {formatDate(profile.last_stank_at)}
				</div>
			{/if}
		</div>

		<!-- Badges -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Badges</h2>
			{#if profile.badges.length}
				<div class="flex flex-wrap gap-2">
					{#each profile.badges as badge}
						<div class="badge" title={badge.description}>
							<span>{badge.icon}</span>
							<span>{badge.name}</span>
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-muted">No badges yet.</p>
			{/if}
		</div>
	{:else}
		<div class="panel">
			<p class="text-muted">Player not found.</p>
		</div>
	{/if}

	<a href={base} class="btn btn-secondary w-full text-center">← Back to Board</a>
</div>