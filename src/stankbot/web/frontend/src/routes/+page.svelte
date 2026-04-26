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

	const isLoggedIn = $derived(Boolean(data.user));

	if (browser && untrack(() => data.state)) {
		boardState.set(untrack(() => data.state));
	}

	const initialBoard = untrack(() => data.state) as BoardState | null;
	const board = $derived($boardState ?? initialBoard);
	const isLoading = $derived(!board);

	const PAGE_SIZE = 20;
	let extraRankings: PlayerRow[] = $state([]);
	let loadOffset = $state(untrack(() => (board?.rankings ?? []).length));
	let hasMore = $state(untrack(() => (board?.rankings ?? []).length >= PAGE_SIZE));
	let loadingMore = $state(false);

	const mergedRankings = $derived<PlayerRow[]>([...(board?.rankings ?? []), ...extraRankings]);
	const displayedRankings = $derived(
		[...mergedRankings].sort((a, b) => {
			const na = a.net ?? a.earned_sp - a.punishments;
			const nb = b.net ?? b.earned_sp - b.punishments;
			return nb - na;
		})
	);

	let prevChainLen = $state(untrack(() => board?.current ?? 0));

	// Stat tile flash tracking
	let flashReactions = $state(false);
	let flashCurrent = $state(false);
	let flashRecord = $state(false);

	let prevReactions = $state(untrack(() => board?.reactions ?? 0));
	let prevCurrent = $state(untrack(() => board?.current ?? 0));
	let prevRecord = $state(untrack(() => board?.record ?? 0));

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
		if (!hasMore) return;
		const el = untrack(() => sentinelEl);
		if (!el) return;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting) {
					loadMoreRankings();
				}
			},
			{ rootMargin: '200px' }
		);
		observer.observe(el);
		return () => observer.disconnect();
	});

	import { formatResetTime } from '$lib/datetime';

	function formatNumber(n: number): string {
		if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
		if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
		return n.toString();
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

{#if !isLoggedIn}
	<!-- Welcome / Landing Page -->
	<div class="relative min-h-[calc(100vh-57px)] flex items-center justify-center overflow-hidden">
		<!-- Background image -->
		<div
			class="absolute inset-0 bg-cover bg-center bg-no-repeat"
			style="background-image: url('/background.png');"
		></div>
		<!-- Dark gradient overlay -->
		<div class="absolute inset-0 bg-gradient-to-b from-bg/80 via-bg/60 to-bg/90"></div>
		<!-- Accent glow -->
		<div class="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(164,124,255,0.08)_0%,transparent_70%)]"></div>

		<div class="relative z-10 flex flex-col items-center text-center px-6 max-w-lg">
			<!-- Stank icon with pulse -->
			<div class="mb-6 relative">
				<div class="absolute inset-0 rounded-full bg-accent/20 blur-xl animate-pulse"></div>
				<img
					src="/stank.gif"
					alt="Stank"
					class="w-20 h-20 relative drop-shadow-[0_0_20px_rgba(164,124,255,0.4)]"
				/>
			</div>

			<!-- Title -->
			<h1 class="text-3xl sm:text-4xl font-bold text-text mb-2 tracking-tight">
				MAPHRA Discord community
			</h1>
			<p class="text-accent font-semibold text-lg sm:text-xl mb-4 tracking-wide uppercase">
				#altar bot
			</p>

			<!-- Tagline -->
			<p class="text-muted text-sm sm:text-base mb-8 max-w-sm leading-relaxed">
				Build chains. Earn points. Rise on the leaderboard.
				<br />
				<span class="text-text/60">Stank responsibly, friends.</span>
				<br />
				<span class="mt-3 text-xs text-muted/50 italic">with love, StankBot and crew</span>
			</p>

			<!-- Discord Login Button -->
			<a
				href="/auth/login"
				class="group relative inline-flex items-center gap-3 px-6 py-3 rounded-lg font-semibold text-white transition-all duration-200
					bg-[#5865F2] hover:bg-[#4752C4] hover:shadow-[0_0_24px_rgba(88,101,242,0.35)] active:scale-[0.98]"
			>
				<svg class="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden="true">
					<path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z" />
				</svg>
				Continue with Discord
				<span class="absolute inset-0 rounded-lg ring-1 ring-white/10 group-hover:ring-white/20 transition-colors"></span>
			</a>

			<!-- Subtle footer -->
			<p class="mt-10 text-xs text-muted/50">
				Sign in with your Discord account to access the live stank leaderboard, track your points, and see how you stack up against other stankers in the MAPHRA community.
			</p>
		</div>
	</div>
{:else}
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
				<span class="text-text">{formatResetTime(board?.next_reset_at ?? null)}</span>
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
						<LeaderboardRow {rank} {row} {isMe} />
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
	{#if board && data.user}
		{@const userId = data.user.id}
		{#if !displayedRankings.some((r) => r.user_id === userId)}
			{@const myRank = getPlayerRank(displayedRankings, userId)}
			{#if myRank}
				<div class="panel">
					<a href={getPlayerUrl(userId)} class="flex items-center justify-between">
						<div>
							<div class="text-muted text-sm">Your rank</div>
							<div class="text-xl font-bold">#{myRank}</div>
						</div>
						<span class="text-accent">→</span>
					</a>
				</div>
			{/if}
		{/if}
	{/if}
</div>
{/if}
