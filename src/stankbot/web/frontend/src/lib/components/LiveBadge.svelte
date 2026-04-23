<script lang="ts">
	import { connectionStatus } from '$lib/stores';
	import { page } from '$app/stores';

	let popoverOpen = $state(false);
	let rootEl: HTMLDivElement;

	const status = $derived($connectionStatus);
	const color = $derived(
		status === 'connected'
			? 'bg-ok'
			: status === 'connecting'
				? 'bg-muted'
				: 'bg-danger'
	);
	const pulse = $derived(status === 'connected' ? 'animate-pulse' : '');
	const label = $derived(
		status === 'connected'
			? 'Receiving live updates.'
			: status === 'connecting'
				? 'Connecting to live updates…'
				: 'Connection lost — refresh to reconnect.'
	);

	function togglePopover(e: MouseEvent) {
		e.stopPropagation();
		popoverOpen = !popoverOpen;
	}

	function handleDocClick(e: MouseEvent) {
		if (!popoverOpen) return;
		if (rootEl && !rootEl.contains(e.target as Node)) popoverOpen = false;
	}

	$effect(() => {
		if (!popoverOpen) return;
		document.addEventListener('click', handleDocClick);
		const t = window.setTimeout(() => (popoverOpen = false), 3000);
		return () => {
			document.removeEventListener('click', handleDocClick);
			window.clearTimeout(t);
		};
	});

	$effect(() => {
		void $page.url.pathname;
		popoverOpen = false;
	});
</script>

<div bind:this={rootEl} class="relative inline-flex items-center">
	<button
		type="button"
		onclick={togglePopover}
		title={label}
		aria-label={label}
		aria-describedby="live-badge-popover"
		class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs text-muted hover:text-text hover:bg-border/40 transition-colors"
		data-testid="live-badge"
		role="status"
		aria-live="polite"
	>
		<span class="hidden sm:inline">Live updates</span>
		<span class="w-2 h-2 rounded-full {color} {pulse}" data-testid="connection-dot"></span>
	</button>

	{#if popoverOpen}
		<div
			id="live-badge-popover"
			role="tooltip"
			class="absolute top-full right-0 mt-2 z-50 w-56 px-3 py-2 bg-panel border border-border rounded-lg shadow-xl text-xs text-text"
		>
			{label}
		</div>
	{/if}
</div>
