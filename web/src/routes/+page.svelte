<script lang="ts">
	import { base } from '$app/paths';
	import { apiFetch } from '$lib/api';
	import type { BoardState, PlayerRow } from '../app.d';

	let { data } = $props();

	const board = $derived(data.state as BoardState | null);
	const isLoading = $derived(!board);
	const liveChain = $derived(board?.current ?? 0);
	const liveUnique = $derived(board?.current_unique ?? 0);

	let displayedRankings: PlayerRow[] = $state([]);
	let loadOffset = $state(0);
	let hasMore = $state(true);
	let loadingMore = $state(false);
	const PAGE_SIZE = 20;

	$effect(() => {
		if (board) {
			displayedRankings = board.rankings ?? [];
			loadOffset = displayedRankings.length;
			hasMore = displayedRankings.length >= PAGE_SIZE;
		}
	});

	async function loadMoreRankings() {
		if (loadingMore || !hasMore || !board) return;
		loadingMore = true;
		try {
			const more = await apiFetch<PlayerRow[]>(`/v2/api/leaderboard?offset=${loadOffset}&limit=${PAGE_SIZE}`);
			if (more.length < PAGE_SIZE) {
				hasMore = false;
			}
			displayedRankings = [...displayedRankings, ...more];
			loadOffset += more.length;
		} catch {
			hasMore = false;
		} finally {
			loadingMore = false;
		}
	}

	let sentinelEl: HTMLDivElement | undefined = $state();

	$effect(() => {
		if (!sentinelEl || !hasMore || loadingMore) return;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting) {
					loadMoreRankings();
				}
			},
			{ rootMargin: '200px' }
		);
		observer.observe(sentinelEl);
		return () => observer.disconnect();
	});

	function formatNumber(n: number): string {
		if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
		if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
		return n.toString();
	}

	function formatNextReset(dateStr: string | null): string {
		if (!dateStr) return '—';
		const date = new Date(dateStr);
		return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }) + ' UTC';
	}

	function getPlayerRank(rankings: PlayerRow[], userId: number): number | null {
		for (let i = 0; i < rankings.length; i++) {
			if (rankings[i].user_id === userId) return i + 1;
		}
		return null;
	}

	function getPlayerUrl(userId: number): string {
		return `${base}/player/${userId}`;
	}
</script>

<div class="p-4 space-y-4">
	<!-- Chain Status Card -->
	<div class="panel">
		<div class="flex items-center justify-between mb-3">
			<div>
				<h1 class="text-xl font-bold flex items-center gap-2">
					<img src="/static/Stank.gif" alt="Stank" class="w-6 h-6" />
					{data.guild_name}
				</h1>
				<p class="text-muted text-sm mt-1">
					{#if liveChain > 0}
						Live chain: <span class="text-accent font-semibold">{liveChain}</span> stanks · <span>{liveUnique}</span> unique
					{:else}
						No active chain
					{/if}
				</p>
			</div>
		</div>

		<!-- Stats Grid -->
		<div class="grid grid-cols-3 gap-3">
			<div class="text-center">
				<div class="text-xl font-bold text-accent">{formatNumber(board?.current ?? 0)}</div>
				<div class="text-xs text-muted uppercase">Current</div>
			</div>
			<div class="text-center">
				<div class="text-xl font-bold">{formatNumber(board?.record ?? 0)}</div>
				<div class="text-xs text-muted uppercase">Session</div>
			</div>
			<div class="text-center">
				<div class="text-xl font-bold">{formatNumber(board?.alltime_record ?? 0)}</div>
				<div class="text-xs text-muted uppercase">All-time</div>
			</div>
		</div>

		<div class="mt-3 pt-3 border-t border-border">
			<div class="text-xs text-muted">
				Next reset: <span class="text-text">{formatNextReset(board?.next_reset_at ?? null)}</span>
			</div>
		</div>
	</div>

	<!-- Quick Links -->
	{#if board?.chain_starter || board?.chainbreaker}
		<div class="grid grid-cols-2 gap-3">
			{#if board.chain_starter}
				{@const starter = board.chain_starter}
				<a href={getPlayerUrl(starter.user_id)} class="panel flex items-center gap-3">
					<div class="text-2xl">🏃</div>
					<div>
						<div class="text-xs text-muted uppercase">Starter</div>
						<div class="font-medium truncate">{starter.display_name}</div>
						<div class="text-sm text-muted">{starter.earned_sp} SP</div>
					</div>
				</a>
			{/if}
			{#if board.chainbreaker}
				{@const breaker = board.chainbreaker}
				<a href={getPlayerUrl(breaker.user_id)} class="panel flex items-center gap-3">
					<div class="text-2xl">💀</div>
					<div>
						<div class="text-xs text-muted uppercase">Breaker</div>
						<div class="font-medium truncate">{breaker.display_name}</div>
						<div class="text-sm text-muted">{breaker.punishments} PP</div>
					</div>
				</a>
			{/if}
		</div>
	{/if}

	<!-- Leaderboard -->
	<div class="panel">
		<h2 class="text-lg font-semibold mb-3">Leaderboard</h2>

		{#if isLoading}
			<div class="space-y-3">
				{#each Array(5) as _}
					<div class="flex items-center gap-3 animate-pulse">
						<div class="w-8 h-8 bg-border rounded-full"></div>
						<div class="flex-1">
							<div class="h-4 bg-border rounded w-24 mb-2"></div>
							<div class="h-3 bg-border rounded w-16"></div>
						</div>
					</div>
				{/each}
			</div>
		{:else if !displayedRankings.length}
			<p class="text-muted text-center py-8">No stanks recorded yet.</p>
		{:else}
			<div class="space-y-2">
				{#each displayedRankings as row, i}
					{@const rank = i + 1}
					{@const userId = data.user?.id}
					{@const isMe = userId && row.user_id === Number(userId)}
					<a
						href={getPlayerUrl(row.user_id)}
						class="flex items-center gap-3 p-2 -mx-2 rounded-lg transition-colors
							{isMe ? 'bg-accent/20' : 'hover:bg-border/50'}"
					>
						<div
							class="w-8 h-8 flex items-center justify-center rounded-full text-sm font-bold
								{rank === 1 ? 'bg-gold text-bg' : ''}
								{rank === 2 ? 'bg-gray-300 text-bg' : ''}
								{rank === 3 ? 'bg-amber-600 text-white' : ''}
								{rank > 3 ? 'bg-border text-muted' : ''}"
						>
							{rank}
						</div>
						<div class="flex-1 min-w-0">
							<div class="font-medium truncate {isMe ? 'text-accent' : ''}">{row.display_name}</div>
							<div class="text-xs text-muted">
								{row.earned_sp} SP · {row.punishments} PP · <span class="font-semibold">{row.earned_sp - row.punishments}</span> net
							</div>
						</div>
						{#if isMe}
							<span class="badge text-accent">You</span>
						{/if}
					</a>
				{/each}
			</div>
			{#if hasMore || loadingMore}
				<div bind:this={sentinelEl} class="flex justify-center py-4">
					{#if loadingMore}
						<div class="animate-pulse text-muted text-sm">Loading more...</div>
					{/if}
				</div>
			{/if}
		{/if}
	</div>

	<!-- Your Rank (if not in loaded rankings) -->
	{#if board && data.user && !displayedRankings.some(r => r.user_id === Number(data.user.id))}
		{@const myRank = getPlayerRank(displayedRankings, Number(data.user.id))}
		{#if myRank}
			<div class="panel">
				<a href={getPlayerUrl(Number(data.user.id))} class="flex items-center justify-between">
					<div>
						<div class="text-muted text-sm">Your rank</div>
						<div class="text-xl font-bold">#{myRank}</div>
					</div>
					<span class="text-accent">→</span>
				</a>
			</div>
		{/if}
	{/if}
</div>