<script lang="ts">
	import '../app.css';
	import { base } from '$app/paths';
	import { browser } from '$app/environment';
	import {
		user,
		guildId,
		guilds,
		toasts,
		removeToast,
		addToast,
		lastWsEvent,
		adminSidebarOpen
	} from '$lib/stores';
	import type { WsEvent } from '$lib/stores';
	import { page } from '$app/stores';
	import { navigating } from '$app/stores';
	import { connect, disconnect } from '$lib/ws';
	import type { User, GuildInfo } from '$lib/types';
	import UserMenu from '$lib/components/UserMenu.svelte';
	import LiveBadge from '$lib/components/LiveBadge.svelte';

	let { data, children } = $props();

	const userData = $derived(data.user as User | null);
	const guildIdData = $derived((data.guild_id as string | null) ?? null);
	const guildList = $derived((data.guilds as GuildInfo[] | undefined) ?? []);
	const isAdmin = $derived(Boolean(data.is_admin));

	let updateToast = $state<{ serverVersion: string; clientVersion: string } | null>(null);

	$effect(() => {
		user.set(userData);
		guildId.set(guildIdData);
		guilds.set(guildList);
	});

	$effect(() => {
		const event = $lastWsEvent;
		if (!event) return;
		handleWsEvent(event);
	});

	// Only reconnect when the user ID actually changes (login/logout),
	// not on every navigation that reloads layout data.
	const userId = $derived(userData?.id ?? null);
	let connectedUserId: string | null = null;

	$effect(() => {
		if (userId && userId !== connectedUserId) {
			connectedUserId = userId;
			connect();
		} else if (!userId) {
			connectedUserId = null;
			disconnect();
		}
	});

	function handleWsEvent(event: WsEvent): void {
		switch (event.kind) {
			case 'achievement':
				addToast(`Achievement unlocked: ${event.badge.name}!`, 'success');
				break;
			case 'session':
				addToast(
					event.action === 'start'
						? `Session ${event.sessionId} started`
						: `Session ${event.sessionId} ended`,
					'info'
				);
				break;
			case 'update-available':
				updateToast = { serverVersion: event.serverVersion, clientVersion: event.clientVersion };
				break;
			case 'connected':
			case 'reconnect-failed':
			case 'disconnected':
				// LiveBadge surfaces transport state — no toast.
				break;
		}
	}

	function reloadPage(): void {
		window.location.reload();
	}

	void browser;

	const pathname = $derived($page.url.pathname);
	const isAdminRoute = $derived(pathname.startsWith(`${base}/admin`) || pathname.startsWith('/admin'));
	const mainClass = $derived(isAdminRoute ? 'flex-1' : 'flex-1 w-full max-w-3xl mx-auto');
</script>

<div class="min-h-screen flex flex-col">
	<!-- Global loading bar -->
	{#if $navigating}
		<div
			class="fixed top-0 left-0 right-0 z-[70] h-0.5 bg-accent animate-pulse pointer-events-none"
			role="status"
			aria-label="Loading"
		></div>
	{/if}

	<!-- Header (single row) -->
	<header class="sticky top-0 z-40 bg-panel border-b border-border">
		<div class="flex items-center justify-between px-4 py-3 gap-3">
			<div class="flex items-center gap-2 shrink-0">
				{#if isAdminRoute}
					<button
						type="button"
						class="flex items-center justify-center w-8 h-8 rounded-md text-muted hover:text-text hover:bg-border/50 transition-colors"
						onclick={() => adminSidebarOpen.update(v => !v)}
						aria-label="Toggle admin menu"
					>
						<span class="text-lg">☰</span>
					</button>
				{/if}
				<a href="{base}/" class="flex items-center gap-2 shrink-0">
					<img src="/stank.gif" alt="Stank" class="w-6 h-6" />
					<span class="font-semibold text-text">StankBot</span>
				</a>
			</div>

			<div class="flex items-center gap-2 shrink-0">
				<LiveBadge disabled={!$user} />
				{#if $user}
					<UserMenu
						user={$user}
						guilds={guildList}
						activeGuildId={guildIdData}
						{isAdmin}
						onerror={(msg) => addToast(msg, 'error')}
					/>
				{:else}
					<a
						href="/auth/login"
						class="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-border/50 transition-colors"
						aria-label="Login"
					>
						<div
							class="w-6 h-6 rounded-full bg-border text-muted flex items-center justify-center text-xs font-semibold"
							aria-hidden="true"
						>?</div>
						<span class="text-sm text-muted hover:text-text hidden sm:inline">Login</span>
					</a>
				{/if}
			</div>
		</div>
	</header>

	<!-- Main Content -->
	<main class={mainClass}>
		{@render children()}
	</main>

	<!-- Toasts -->
	{#if $toasts.length > 0}
		<div
			class="fixed bottom-4 right-4 sm:right-4 inset-x-4 sm:inset-x-auto z-[60] flex flex-col gap-2 pointer-events-none items-stretch sm:items-end max-w-full sm:max-w-sm sm:ml-auto"
		>
			{#each $toasts as toast (toast.id)}
				<div
					class="pointer-events-auto px-4 py-3 rounded-lg shadow-lg backdrop-blur-md
						{toast.type === 'success' ? 'bg-ok/90 text-bg' : ''}
						{toast.type === 'error' ? 'bg-danger/90 text-white' : ''}
						{toast.type === 'warning' ? 'bg-gold/90 text-bg' : ''}
						{toast.type === 'info' ? 'bg-panel/90 text-text' : ''}"
					role="alert"
				>
					<div class="flex items-center justify-between gap-2">
						<span>{toast.message}</span>
						<button onclick={() => removeToast(toast.id)} class="text-lg">&times;</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Update available toast (persistent, bottom-center) -->
	{#if updateToast}
		<div
			class="fixed bottom-4 left-1/2 -translate-x-1/2 z-[61] pointer-events-auto"
			data-testid="update-toast"
			role="alert"
		>
			<div class="flex items-center gap-3 px-5 py-3 rounded-lg shadow-lg backdrop-blur-md bg-accent/95 text-bg">
				<span>A new version is available.</span>
				<button
					onclick={reloadPage}
					class="px-3 py-1 rounded-md bg-bg/20 hover:bg-bg/30 font-semibold text-sm transition-colors"
					data-testid="update-reload-btn"
				>
					Reload
				</button>
			</div>
		</div>
	{/if}
</div>
