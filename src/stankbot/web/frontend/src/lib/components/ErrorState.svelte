<script lang="ts">
	import Button from './Button.svelte';

	interface Props {
		title?: string;
		message?: string;
		onretry?: () => void;
	}

	let {
		title = 'Something went wrong',
		message = 'The data failed to load. Try again.',
		onretry
	}: Props = $props();
</script>

<div class="flex flex-col items-center justify-center py-10 text-center">
	<div class="text-4xl mb-2" aria-hidden="true">⚠️</div>
	<h3 class="text-lg font-semibold text-danger">{title}</h3>
	<p class="text-sm text-muted mt-1 max-w-md">{message}</p>
	{#if onretry}
		<div class="mt-4">
			<Button variant="secondary" onclick={onretry}>Retry</Button>
		</div>
	{/if}
</div>
