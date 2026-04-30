<script lang="ts">
	import { toasts, removeToast } from '$lib/stores';

	interface Props {
		updateToast?: { serverVersion: string; clientVersion: string } | null;
		onreload?: () => void;
	}

	let { updateToast = null, onreload }: Props = $props();
</script>

{#if $toasts.length > 0}
	<div
		class="fixed bottom-4 right-4 sm:right-4 inset-x-4 sm:inset-x-auto z-[60] flex flex-col gap-2 pointer-events-none items-stretch sm:items-end max-w-full sm:max-w-sm sm:ml-auto"
	>
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

<!-- Update available toast (persistent, bottom-center) -->
{#if updateToast}
	<div
		class="fixed flex flex-col items-center w-full bottom-4 z-[61] pointer-events-auto"
		data-testid="update-toast"
		role="alert"
	>
		<div class="flex items-center gap-3 px-4 py-2 rounded-lg shadow-lg backdrop-blur-md bg-accent/95 text-bg">
			<span class="text-sm sm:text-base">Updated available!</span>
			<button
				onclick={onreload}
				class="px-3 py-2 rounded-md bg-bg/20 hover:bg-bg/30 font-semibold text-sm transition-colors"
				data-testid="update-reload-btn"
			>
				Reload
			</button>
		</div>
	</div>
{/if}
