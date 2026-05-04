<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import type { PlayerProfile, User, PlayerChainEntry } from '$lib/types';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import Sparkline from '$lib/components/Sparkline.svelte';
	import StatTile from '$lib/components/StatTile.svelte';
	import Avatar from '$lib/components/Avatar.svelte';

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
	const recentChains = $derived((data.recentChains as PlayerChainEntry[] | undefined) ?? []);
	const isLoading = $derived(!profile);
	const targetId = $derived($page.params.id || userData?.id);

	const spSeries = $derived(history.map((p) => p.sp));
	const ppSeries = $derived(history.map((p) => p.pp));
	const netSeries = $derived(history.map((p) => p.sp - p.pp));

	import { formatDateTime } from '$lib/datetime';
	import { formatNumber } from '$lib/format';

	let containerWidth = $state(0);

	function getContainerWidthForCharts() {
		return containerWidth >= 574 ? containerWidth >= 702 ? 702 / 3 : (containerWidth / 3) : containerWidth;
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
		<!-- Header with avatar + rank -->
		<header class="flex items-center gap-3 mb-4">
			<Avatar name={profile.display_name} userId={profile.user_id} discordAvatar={profile.discord_avatar} size="md" />
			<div>
				<div class="flex items-center gap-2">
					<h1 class="text-2xl font-bold text-text">{profile.display_name}</h1>
					{#if profile.rank}
						<span class="text-xs font-semibold text-accent border border-accent/30 rounded-full px-2 py-0.5">#{profile.rank}</span>
					{/if}
				</div>
				<p class="text-sm text-muted">Player #{targetId}</p>
			</div>
		</header>

		<!-- Session Stats -->
		<div class="panel" data-testid="session-stats">
			<h2 class="text-lg font-semibold mb-3">Session</h2>
			<div class="grid grid-cols-3 gap-3">
				<StatTile value={formatNumber(profile.session.earned_sp)} label="SP" color="text-accent" valueTestId="session-sp" />
				<StatTile value={formatNumber(profile.session.punishments)} label="PP" color="text-danger" valueTestId="session-pp" />
				<StatTile value={formatNumber(profile.session.net)} label="Net" color={profile.session.net >= 0 ? 'text-ok' : 'text-danger'} valueTestId="session-net" />
			</div>
		</div>

		<!-- All-time Stats -->
		<div class="panel" data-testid="alltime-stats">
			<h2 class="text-lg font-semibold mb-3">All-time</h2>
			<div class="grid grid-cols-2 gap-3 mb-3">
				<StatTile value={formatNumber(profile.alltime.earned_sp)} label="SP" color="text-accent" valueTestId="alltime-sp" />
				<StatTile value={formatNumber(profile.alltime.punishments)} label="PP" color="text-danger" valueTestId="alltime-pp" />
				<StatTile value={String(profile.alltime.chains_started)} label="Started" valueTestId="alltime-started" color="text-text" />
				<StatTile value={String(profile.alltime.chains_broken)} label="Broken" valueTestId="alltime-broken" color="text-text" />
			</div>

			<!-- Streak -->
			<div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted pt-3 border-t border-border">
				{#if profile.stank_streak.current > 0}
					<span>🔥 Current streak: {profile.stank_streak.current} days</span>
				{/if}
				{#if profile.stank_streak.longest > 0}
					<span>⚡ Longest streak: {profile.stank_streak.longest} days</span>
				{/if}
				{#if profile.last_stank_at}
					<span>Last stank: {formatDateTime(profile.last_stank_at)}</span>
				{/if}
			</div>
		</div>

		<!-- History sparklines -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Last 30 days</h2>
			{#if history.length}
				<div class="grid grid-cols-1 sm:grid-cols-3 gap-4" bind:clientWidth={containerWidth}>
					<div>
						<div class="text-xs text-muted uppercase mb-1">SP / day</div>
						<div class="text-accent">
							
							<Sparkline values={spSeries} width={getContainerWidthForCharts()} height={getContainerWidthForCharts() / 4} ariaLabel="SP per day" />
						</div>
					</div>
					<div>
						<div class="text-xs text-muted uppercase mb-1">PP / day</div>
						<div class="text-danger">
							<Sparkline values={ppSeries} width={getContainerWidthForCharts()} height={getContainerWidthForCharts() / 4} ariaLabel="PP per day" />
						</div>
					</div>
					<div>
						<div class="text-xs text-muted uppercase mb-1">Net</div>
						<div class="text-ok">
							<Sparkline values={netSeries} width={getContainerWidthForCharts()} height={getContainerWidthForCharts() / 4} ariaLabel="Net per day" />
						</div>
					</div>
				</div>
			{:else}
				<p class="text-muted text-sm">No activity recorded in the last 30 days.</p>
			{/if}
		</div>

		<!-- Recent Chains -->
		{#if recentChains.length > 0}
			<details class="panel">
				<summary class="text-lg font-semibold cursor-pointer select-none">Recent Chains ({recentChains.length})</summary>
				<div class="mt-3 space-y-1">
					{#each recentChains as c}
						<a href="{base}/chain/{c.chain_id}" class="flex items-center justify-between px-2 py-2 rounded-md hover:bg-border/40 text-sm">
							<div class="flex items-center gap-3 min-w-0">
								<span class="font-mono text-xs text-muted shrink-0">#{c.chain_id}</span>
								<span class="truncate">{formatDateTime(c.started_at)}</span>
							</div>
							<span class="shrink-0 text-xs text-muted tabular-nums">
								{c.length} · {c.user_stanks} stanks
							</span>
						</a>
					{/each}
				</div>
			</details>
		{/if}

		<!-- Achievement gallery -->
		<div class="panel">
			<h2 class="text-lg font-semibold mb-3">Achievements</h2>
			{#if achievements.length}
				{@const earnedCount = achievements.filter((a) => a.unlocked).length}
				<p class="text-xs text-muted mb-3">{earnedCount} of {achievements.length} unlocked</p>
				<div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
					{#each achievements as a (a.key)}
						<div
							class="flex items-start gap-1 p-2 rounded-md border border-border
								{a.unlocked ? 'bg-panel' : 'bg-bg opacity-50'}"
							title={a.description}
						>
							<span class="text-2xl leading-none">{a.icon}</span>
							<div class="min-w-0">
								<div class="font-medium text-sm">{a.name}</div>
								<div class="text-xs text-muted">{a.description}</div>
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