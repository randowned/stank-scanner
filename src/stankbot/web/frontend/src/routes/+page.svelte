<script lang="ts">
	import { base } from '$app/paths';
	import { browser } from '$app/environment';
	import { flip } from 'svelte/animate';
	import { untrack } from 'svelte';
	import { apiFetch } from '$lib/api';
	import { boardState, activeChainBreak } from '$lib/stores';
	import type { BoardState, PlayerRow } from '$lib/types';
	import LeaderboardRow from '$lib/components/LeaderboardRow.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import ChainBreakOverlay from '$lib/components/ChainBreakOverlay.svelte';

	let { data } = $props();

	if (browser && data.state) {
		boardState.set(data.state);
	}

	const initialBoard = data.state as BoardState | null;
	const board = $derived($boardState ?? initialBoard);
	const isLoading = $derived(!board);

	const PAGE_SIZE = 20;
	let extraRankings: PlayerRow[] = $state([]);
	let loadOffset = $state((board?.rankings ?? []).length);
	let hasMore = $state((board?.rankings ?? []).length >= PAGE_SIZE);
	let loadingMore = $state(false);

	const mergedRankings = $derived<PlayerRow[]>([...(board?.rankings ?? []), ...extraRankings]);
	const displayedRankings = $derived(
		[...mergedRankings].sort((a, b) => {
			const na = a.net ?? a.earned_sp - a.punishments;
			const nb = b.net ?? b.earned_sp - b.punishments;
			return nb - na;
		})
	);

	let prevChainLen = $state(board?.current ?? 0);

	// Stat tile flash tracking
	let flashReactions = $state(false);
	let flashCurrent = $state(false);
	let flashRecord = $state(false);

	let prevReactions = $state(board?.reactions ?? 0);
	let prevCurrent = $state(board?.current ?? 0);
	let prevRecord = $state(board?.record ?? 0);

	function triggerFlash(setter: (v: boolean) => void) {
		setter(true);
		setTimeout(() => setter(false), 900);
	}

	$effect(() => {
		if (!board) return;
		if (board.reactions !== untrack(() => prevReactions)) {
			prevReactions = board.reactions;
			triggerFlash((v) => (flashReactions = v));
		}
		if (board.current !== untrack(() => prevCurrent)) {
			prevCurrent = board.current;
			triggerFlash((v) => (flashCurrent = v));
		}
		if (board.record !== untrack(() => prevRecord)) {
			prevRecord = board.record;
			triggerFlash((v) => (flashRecord = v));
		}
	});

	$effect(() => {
		if (!board) return;
		const current = board.current;
		const prev = untrack(() => prevChainLen);
		if (prev > 0 && current === 0 && board.chainbreaker) {
			const breaker = board.chainbreaker;
			activeChainBreak.set({
				user_id: breaker.user_id,
				display_name: breaker.display_name,
				avatar_url: null,
				pp_loss: breaker.punishments
			});
		} else if (current > 0) {
			activeChainBreak.set(null);
		}
		prevChainLen = current;
	});

	async function loadMoreRankings() {
		if (loadingMore || !hasMore || !board) return;
		loadingMore = true;
		try {
			const more = await apiFetch<PlayerRow[]>(`/api/leaderboard?offset=${loadOffset}&limit=${PAGE_SIZE}`);
			if (more.length < PAGE_SIZE) {
				hasMore = false;
			}
			extraRankings = [...extraRankings, ...more];
			loadOffset += more.length;
		} catch {
			hasMore = false;
		} finally {
			loadingMore = false;
		}
	}

	let sentinelEl: HTMLDivElement | undefined = $state();

	$effect(() => {
		if (!sentinelEl || !hasMore) return;
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
		return (
			date.toLocaleString('en-US', {
				month: 'short',
				day: 'numeric',
				hour: 'numeric',
				minute: '2-digit',
				timeZone: 'UTC'
			}) + ' UTC'
		);
	}

	function getPlayerRank(rankings: PlayerRow[], userId: string): number | null {
		for (let i = 0; i < rankings.length; i++) {
			if (rankings[i].user_id === userId) return i + 1;
		}
		return null;
	}

	function getPlayerUrl(userId: string | number): string {
		return `${base}/player/${userId}`;
	}
</script>

<div class="p-4 flex flex-col gap-4">
	<!-- Chain Status Card -->
	<div class="panel relative">
		<ChainBreakOverlay />
		<div class="flex items-center justify-between mb-3">
			<div>
				<h1 class="text-xl font-bold flex items-center gap-2" data-testid="guild-name">
					<img src="/stank.gif" alt="Stank" class="w-6 h-6" />
					{data.guild_name}
				</h1>
			</div>
		</div>

		<!-- Stats Grid -->
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
			<div class="text-center cursor-default" data-testid="tile-reactions"
				title="Chain reactions / Session reactions">
				<div class="text-xl font-bold text-accent {flashReactions ? 'row-flash' : ''}">
					{formatNumber(board?.reactions ?? 0)} / {formatNumber(board?.session_reactions ?? 0)}
				</div>
				<div class="text-xs text-muted uppercase">Reactions</div>
			</div>
			<div class="text-center cursor-default" data-testid="tile-current"
				title="Current chain length / Unique stankers in chain">
				<div class="text-xl font-bold text-accent {flashCurrent ? 'row-flash' : ''}" data-testid="chain-counter">
					{formatNumber(board?.current ?? 0) + ' / ' + formatNumber(board?.current_unique ?? 0)}
				</div>
				<div class="text-xs text-muted uppercase">Current</div>
			</div>
			<div class="text-center cursor-default" data-testid="tile-session"
				title="Session record chain length / Unique stankers in that chain">
				<div class="text-xl font-bold {flashRecord ? 'row-flash' : ''}">
					{formatNumber(board?.record ?? 0) + ' / ' + formatNumber(board?.record_unique ?? 0)}
				</div>
				<div class="text-xs text-muted uppercase">Session</div>
			</div>
			<div class="text-center cursor-default" data-testid="tile-alltime"
				title="All-time record chain length / Unique stankers in that chain">
				<div class="text-xl font-bold">
					{formatNumber(board?.alltime_record ?? 0) + ' / ' + formatNumber(board?.alltime_record_unique ?? 0)}
				</div>
				<div class="text-xs text-muted uppercase">All-time</div>
			</div>
		</div>

		<div class="mt-3 pt-3 border-t border-border">
			<div class="text-xs text-muted">
				Next reset:
				<span class="text-text">{formatNextReset(board?.next_reset_at ?? null)}</span>
			</div>
		</div>
	</div>

	<!-- Quick Links -->
	{#if board?.chain_starter || board?.chainbreaker}
		<div class="grid grid-cols-2 gap-4">
			{#if board.chain_starter}
				{@const starter = board.chain_starter}
				<a href={getPlayerUrl(starter.user_id)} class="panel flex flex-col items-center gap-3">
					<div class="text-sm text-muted uppercase">🏃 Starter</div>
					<div class="text-center">
						<div class="font-medium truncate">{starter.display_name}</div>
						<div class="text-sm text-muted">{starter.earned_sp} SP</div>
					</div>
				</a>
			{/if}
			{#if board.chainbreaker}
				{@const breaker = board.chainbreaker}
				<a href={getPlayerUrl(breaker.user_id)} class="panel flex flex-col items-center gap-3">
					<div class="text-sm text-muted uppercase">💀 Breaker</div>
					<div class="text-center">
						<div class="font-medium truncate">{breaker.display_name}</div>
						<div class="text-sm text-muted">-{breaker.punishments} SP</div>
					</div>
				</a>
			{/if}
		</div>
	{/if}

	<!-- Leaderboard -->
	<div class="panel">
		<div class="flex items-center justify-between mb-3">
			<div class="flex items-center gap-2">
				<h2 class="text-lg font-semibold">Leaderboard</h2>
				{#if board?.session_id}
					<a href="{base}/session/{board.session_id}" class="text-xs text-muted hover:text-accent transition-colors">
						Session #{board.session_id}
					</a>
				{/if}
			</div>
			<span class="text-xs text-muted uppercase">Stank Points</span>
		</div>

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
			<EmptyState icon="🏁" title="No stanks yet" message="The leaderboard will fill in as players start stanking." />
		{:else}
			<div class="space-y-2">
				{#each displayedRankings as row, i (row.user_id)}
					{@const rank = i + 1}
					{@const userId = data.user?.id}
					{@const isMe = Boolean(userId && row.user_id === userId)}
					<div animate:flip={{ duration: 280 }}>
						<LeaderboardRow {rank} {row} {isMe} chainLength={board?.current ?? 0} />
					</div>
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
	{#if board && data.user && !displayedRankings.some((r) => r.user_id === data.user.id)}
		{@const myRank = getPlayerRank(displayedRankings, data.user.id)}
		{#if myRank}
			<div class="panel">
				<a href={getPlayerUrl(data.user.id)} class="flex items-center justify-between">
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
