<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

	const sections = [
		{ href: `${base}/admin`, label: 'Dashboard', icon: '🏠' },
		{ href: `${base}/admin/templates`, label: 'Templates', icon: '📝' },
		{ href: `${base}/admin/admins`, label: 'Admins', icon: '👥' },
		{ href: `${base}/admin/audit`, label: 'Audit log', icon: '📋' },
		{ href: `${base}/admin/settings`, label: 'Settings', icon: '⚙️' }
	];

	let sidebarOpen = $state(false);
	const currentPath = $derived($page.url.pathname);
</script>

<div class="flex min-h-[calc(100vh-120px)]">
	<button
		type="button"
		class="md:hidden fixed bottom-4 right-4 z-30 bg-accent text-[#1a1425] rounded-full w-12 h-12 shadow-lg flex items-center justify-center text-xl"
		onclick={() => (sidebarOpen = !sidebarOpen)}
		aria-label="Toggle admin menu"
	>{sidebarOpen ? '×' : '☰'}</button>

	{#if sidebarOpen}
		<div
			class="md:hidden fixed inset-0 z-20 bg-black/60"
			onclick={() => (sidebarOpen = false)}
			onkeydown={(e) => e.key === 'Escape' && (sidebarOpen = false)}
			role="presentation"
		></div>
	{/if}

	<aside
		class="bg-panel border-r border-border p-3 w-56 shrink-0 fixed md:static top-[57px] md:top-0 bottom-0 left-0 z-20 overflow-y-auto transition-transform
			{sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}"
	>
		<div class="text-xs uppercase tracking-wide text-muted mb-2 px-2">Admin</div>
		<nav class="flex flex-col gap-1">
			{#each sections as s (s.href)}
				<a
					href={s.href}
					onclick={() => (sidebarOpen = false)}
					class="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors
						{currentPath === s.href ? 'bg-accent text-[#1a1425]' : 'text-muted hover:text-text hover:bg-border/40'}"
				>
					<span aria-hidden="true">{s.icon}</span>
					<span>{s.label}</span>
				</a>
			{/each}
		</nav>
	</aside>

	<div class="flex-1 p-4 md:p-6 min-w-0">
		{@render children()}
	</div>
</div>
