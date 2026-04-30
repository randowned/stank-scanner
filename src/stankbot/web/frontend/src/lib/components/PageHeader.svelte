<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		subtitle?: string;
		actions?: Snippet;
	}

	let { title, subtitle, actions }: Props = $props();
</script>

<header class="flex flex-wrap items-center justify-between gap-3 mb-4" data-testid="page-header">
	<div>
		<h1 class="text-2xl font-bold text-text">{title}</h1>
		{#if subtitle}
			<p class="text-sm text-muted mt-1">{subtitle}</p>
		{/if}
	</div>
	{#if actions}
		<div class="flex items-center gap-2">{@render actions()}</div>
	{/if}
</header>
