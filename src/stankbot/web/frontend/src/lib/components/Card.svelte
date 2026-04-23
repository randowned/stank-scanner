<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title?: string;
		footer?: Snippet;
		class?: string;
		children: Snippet;
	}

	let { title, footer, class: klass = '', children }: Props = $props();
</script>

<section class="panel {klass}">
	{#if title}
		<header class="flex items-center justify-between mb-3">
			<h2 class="text-lg font-semibold">{title}</h2>
		</header>
	{/if}
	<div>
		{@render children()}
	</div>
	{#if footer}
		<footer class="mt-3 pt-3 border-t border-border">
			{@render footer()}
		</footer>
	{/if}
</section>
