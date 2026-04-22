<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	import { user, guildId, connectionStatus, toasts, removeToast } from '$lib/stores';
	import { onMount } from 'svelte';
	import { connect, disconnect } from '$lib/ws';

	let { data, children } = $props();

	const userData = $derived(data.user as { id: string; username: string; avatar: string | null } | null);
	const guildIdData = $derived(data.guild_id as string | null);
	const isAdmin = $derived($page.url.pathname.startsWith('/v2/admin'));
	const currentPath = $derived($page.url.pathname);

	onMount(() => {
		if (userData) {
			user.set(userData);
			if (guildIdData) {
				guildId.set(guildIdData);
				connect(Number(guildIdData), Number(userData.id));
			}
		}

		return () => {
			disconnect();
		};
	});

	const navItems = $derived([
		{ href: '/v2', label: 'Board', icon: '🏠' },
		{ href: '/v2/chains', label: 'Chains', icon: '⛓️' },
		{ href: '/v2/sessions', label: 'Sessions', icon: '📜' },
		{ href: '/v2/player/' + (userData?.id ?? ''), label: 'Me', icon: '👤' }
	]);

	const adminItems = $derived([
		{ href: '/v2/admin/settings', label: 'Settings', icon: '⚙️' },
		{ href: '/v2/admin/altar', label: 'Altar', icon: '🗿' },
		{ href: '/v2/admin/templates', label: 'Templates', icon: '📝' }
	]);
</script>

<div class="min-h-screen flex flex-col">
	<!-- Header -->
	<header class="sticky top-0 z-50 bg-panel border-b border-border">
		<div class="flex items-center justify-between px-4 py-3">
			<a href="/v2" class="flex items-center gap-2">
				<img src="/static/Stank.gif" alt="Stank" class="w-6 h-6" />
				<span class="font-semibold text-text">StankBot</span>
			</a>

			<div class="flex items-center gap-2">
				{#if $connectionStatus === 'connected'}
					<span class="w-2 h-2 rounded-full bg-ok animate-pulse" title="Live"></span>
				{:else}
					<span class="w-2 h-2 rounded-full bg-muted" title="Offline"></span>
				{/if}
			</div>
		</div>

		<!-- Navigation -->
		<nav class="flex gap-1 px-4 pb-3 overflow-x-auto scrollbar-thin">
			{#each navItems as item}
				<a
					href={item.href}
					class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors
						{currentPath === item.href || currentPath.startsWith(item.href + '/') ? 'bg-accent text-[#1a1425]' : 'text-muted hover:text-text'}"
				>
					<span>{item.icon}</span>
					<span class="whitespace-nowrap">{item.label}</span>
				</a>
			{/each}

			{#if isAdmin && data.is_admin}
				<div class="w-px h-6 bg-border mx-1"></div>
				{#each adminItems as item}
					<a
						href={item.href}
						class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors
							{currentPath.startsWith(item.href) ? 'bg-accent text-[#1a1425]' : 'text-muted hover:text-text'}"
					>
						<span>{item.icon}</span>
						<span class="whitespace-nowrap">{item.label}</span>
					</a>
				{/each}
			{/if}
		</nav>
	</header>

	<!-- Main Content -->
	<main class="flex-1">
		{@render children()}
	</main>

	<!-- Toasts -->
	{#if $toasts.length > 0}
		<div class="fixed bottom-20 left-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
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
</div>