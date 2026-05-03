<script lang="ts">
	import type { Snippet } from 'svelte';
	import { setContext } from 'svelte';

	interface Props {
		open?: boolean;
		align?: 'left' | 'right';
		trigger: Snippet<[{ toggle: () => void; open: boolean }]>;
		children: Snippet;
		onclose?: () => void;
	}

	let { open = $bindable(false), align = 'right', trigger, children, onclose }: Props = $props();

	let rootEl: HTMLDivElement;

	function toggle() {
		open = !open;
	}

	function close() {
		if (open) {
			open = false;
			onclose?.();
		}
	}

	setContext('dropdown', { close });

	function handleDocClick(e: MouseEvent) {
		if (!open) return;
		if (rootEl && !rootEl.contains(e.target as Node)) close();
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
	}

	$effect(() => {
		if (!open) return;
		document.addEventListener('click', handleDocClick);
		document.addEventListener('keydown', handleKey);
		return () => {
			document.removeEventListener('click', handleDocClick);
			document.removeEventListener('keydown', handleKey);
		};
	});
</script>

<div bind:this={rootEl} class="relative inline-block">
	{@render trigger({ toggle, open })}

	{#if open}
		<div
			class="absolute top-full mt-2 z-50 w-max bg-panel border border-border rounded-lg shadow-xl py-1
				{align === 'right' ? 'right-0' : 'left-0'}"
			role="menu"
			data-testid="dropdown-menu"
		>
			{@render children()}
		</div>
	{/if}
</div>
