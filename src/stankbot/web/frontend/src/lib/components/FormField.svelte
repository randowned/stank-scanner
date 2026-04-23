<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		for?: string;
		hint?: string;
		error?: string;
		required?: boolean;
		children: Snippet;
	}

	let { label, for: forId, hint, error, required = false, children }: Props = $props();
</script>

<div class="mb-4">
	<label class="label" for={forId}>
		{label}
		{#if required}<span class="text-danger" aria-hidden="true">*</span>{/if}
	</label>
	{@render children()}
	{#if error}
		<div class="text-xs text-danger mt-1">{error}</div>
	{:else if hint}
		<div class="text-xs text-muted mt-1">{hint}</div>
	{/if}
</div>
