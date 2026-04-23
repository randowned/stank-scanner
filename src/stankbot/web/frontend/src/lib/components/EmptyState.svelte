<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		icon?: string;
		title: string;
		message?: string;
		actions?: Snippet;
	}

	let { icon, title, message, actions }: Props = $props();
</script>

<div class="flex flex-col items-center justify-center py-12 text-center">
	{#if icon}
		<div class="text-5xl mb-3 opacity-60" aria-hidden="true">{icon}</div>
	{/if}
	<h3 class="text-lg font-semibold text-text">{title}</h3>
	{#if message}
		<p class="text-sm text-muted mt-1 max-w-md">{message}</p>
	{/if}
	{#if actions}
		<div class="mt-4 flex gap-2">{@render actions()}</div>
	{/if}
</div>
