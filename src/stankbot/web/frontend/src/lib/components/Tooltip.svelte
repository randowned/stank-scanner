<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		children: Snippet;
		tooltip: Snippet;
	}

	let { children, tooltip }: Props = $props();
</script>

<span
	data-testid="tooltip-root"
	role="button"
	tabindex="0"
	class="group relative inline-flex"
>
	{@render children()}
	<div
		role="tooltip"
		class="invisible group-hover:visible group-focus-within:visible absolute top-full left-1/2 -translate-x-1/2 mt-2 z-50 px-3 py-2 bg-panel border border-border rounded-lg shadow-xl text-xs text-text whitespace-nowrap"
		data-testid="tooltip-popover"
	>
		<div
			class="absolute bottom-full left-1/2 -translate-x-1/2 w-2 h-2 bg-panel border-l border-t border-border rotate-45 -mb-px"
		></div>
		{@render tooltip()}
	</div>
</span>
