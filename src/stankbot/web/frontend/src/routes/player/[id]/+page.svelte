<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import type { PlayerProfile, User } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import Sparkline from '$lib/components/Sparkline.svelte';

	interface HistoryPoint {
		day: string;
		sp: number;
		pp: number;
	}

	interface AchievementEntry {
		key: string;
		name: string;
		description: string;
		icon: string;
		unlocked: boolean;
	}

	let { data } = $props();

	const userData = $derived(data.user as User | null);
	const profile = $derived(data.profile as PlayerProfile | null);
	const history = $derived((data.history as HistoryPoint[] | undefined) ?? []);
	const achievements = $derived((data.achievements as AchievementEntry[] | undefined) ?? []);
	const isLoading = $derived(!profile);
	const targetId = $derived($page.params.id || userData?.id);

	const spSeries = $derived(history.map((p) => p.sp));
	const ppSeries = $derived(history.map((p) => p.pp));
	const netSeries = $derived(history.map((p) => p.sp - p.pp));

	import { formatDateTime } from '$lib/datetime';

	function formatNumber(n: number): string {
		if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
		if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
		return n.toString();
	}
</script>

<div class="p-4 space-y-4">
	{#if isLoading}
		<div class="panel">
			<Skeleton width="8rem" height="1.5rem" />
			<div class="mt-3 space-y-2">
				<Skeleton width="6rem" />
				<Skeleton width="6rem" />
			</div>
		</div>
	{:else if profile}
		<PageHeader title="📈 {profile.display_name}" subtitle="Player #{targetId}" />

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
					Last stank: {formatDateTime(profile.last_stank_at)}
				</div>
			{/if}
		</div>

		<!-- History sparklines -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Last 30 days</h2>
			{#if history.length}
				<div class="grid grid-cols-3 gap-4">
					<div>
						<div class="text-xs text-muted uppercase mb-1">SP / day</div>
						<div class="text-accent">
							<Sparkline values={spSeries} ariaLabel="SP per day" />
						</div>
					</div>
					<div>
						<div class="text-xs text-muted uppercase mb-1">PP / day</div>
						<div class="text-danger">
							<Sparkline values={ppSeries} ariaLabel="PP per day" />
						</div>
					</div>
					<div>
						<div class="text-xs text-muted uppercase mb-1">Net</div>
						<div class="text-ok">
							<Sparkline values={netSeries} ariaLabel="Net per day" />
						</div>
					</div>
				</div>
			{:else}
				<p class="text-muted text-sm">No activity recorded in the last 30 days.</p>
			{/if}
		</div>

		<!-- Achievement gallery -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Achievements</h2>
			{#if achievements.length}
				{@const earnedCount = achievements.filter((a) => a.unlocked).length}
				<p class="text-xs text-muted mb-3">{earnedCount} of {achievements.length} unlocked</p>
				<div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
					{#each achievements as a (a.key)}
						<div
							class="flex items-start gap-2 p-2 rounded-md border border-border
								{a.unlocked ? 'bg-panel' : 'bg-bg opacity-50'}"
							title={a.description}
						>
							<span class="text-2xl leading-none">{a.icon}</span>
							<div class="min-w-0">
								<div class="font-medium text-sm truncate">{a.name}</div>
								<div class="text-xs text-muted line-clamp-2">{a.description}</div>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<EmptyState icon="🏅" title="No achievements available" />
			{/if}
		</div>
	{:else}
		<div class="panel">
			<EmptyState icon="❓" title="Player not found" message="No profile exists for this ID in the current guild." />
		</div>
	{/if}

	<a href={base} class="btn btn-secondary w-full text-center">← Back to Board</a>
</div>