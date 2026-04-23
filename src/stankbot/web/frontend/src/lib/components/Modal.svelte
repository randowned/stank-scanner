<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		open: boolean;
		title?: string;
		size?: 'sm' | 'md' | 'lg' | 'xl';
		onclose?: () => void;
		children: Snippet;
		footer?: Snippet;
	}

	let { open = $bindable(), title, size = 'md', onclose, children, footer }: Props = $props();

	const sizeCls: Record<string, string> = {
		sm: 'max-w-sm',
		md: 'max-w-lg',
		lg: 'max-w-2xl',
		xl: 'max-w-4xl'
	};

	function handleBackdrop() {
		open = false;
		onclose?.();
	}

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) {
			e.stopPropagation();
			open = false;
			onclose?.();
		}
	}
</script>

<svelte:window onkeydown={handleKey} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
		role="dialog"
		aria-modal="true"
		aria-labelledby={title ? 'modal-title' : undefined}
		data-testid="modal-backdrop"
		onclick={handleBackdrop}
		onkeydown={(e) => e.key === 'Enter' && handleBackdrop()}
		tabindex="-1"
	>
		<div
			class="w-full {sizeCls[size]} bg-panel border border-border rounded-lg shadow-xl"
			role="document"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
			tabindex="-1"
		>
			{#if title}
				<header class="px-4 py-3 border-b border-border flex items-center justify-between">
					<h2 id="modal-title" class="text-lg font-semibold">{title}</h2>
					<button
						type="button"
						class="text-muted hover:text-text text-xl leading-none"
						onclick={handleBackdrop}
						aria-label="Close"
					>×</button>
				</header>
			{/if}
			<div class="p-4">
				{@render children()}
			</div>
			{#if footer}
				<footer class="px-4 py-3 border-t border-border flex justify-end gap-2">
					{@render footer()}
				</footer>
			{/if}
		</div>
	</div>
{/if}
