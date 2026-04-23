<script lang="ts">
	import { fade } from 'svelte/transition';
	import { activeChainBreak } from '$lib/stores';
	import Avatar from './Avatar.svelte';
	import { onDestroy } from 'svelte';

	let showDismiss = $state(false);
	let dismissTimer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		if ($activeChainBreak) {
			showDismiss = false;
			if (dismissTimer) clearTimeout(dismissTimer);
			dismissTimer = setTimeout(() => (showDismiss = true), 5000);
		} else {
			showDismiss = false;
			if (dismissTimer) clearTimeout(dismissTimer);
			dismissTimer = null;
		}
	});

	onDestroy(() => {
		if (dismissTimer) clearTimeout(dismissTimer);
	});

	function dismiss() {
		activeChainBreak.set(null);
	}
</script>

{#if $activeChainBreak}
	{@const info = $activeChainBreak}
	<div
		class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 rounded-lg bg-bg/80 backdrop-blur-sm"
		role="status"
		aria-live="polite"
		transition:fade={{ duration: 180 }}
		data-testid="chain-break-overlay"
	>
		<div class="text-xs uppercase tracking-wide text-muted">Chain broken by</div>
		<Avatar src={info.avatar_url} name={info.display_name} size="lg" />
		<div class="text-lg font-semibold text-text">{info.display_name}</div>
		<div class="text-3xl font-bold text-danger tabular-nums">-{info.pp_loss} PP</div>
		{#if showDismiss}
			<button
				type="button"
				onclick={dismiss}
				class="absolute top-2 right-2 text-xs text-muted hover:text-text px-2 py-1 rounded"
				aria-label="Dismiss chain break overlay"
			>
				Dismiss
			</button>
		{/if}
	</div>
{/if}
