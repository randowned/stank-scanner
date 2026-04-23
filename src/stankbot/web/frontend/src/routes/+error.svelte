<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
</script>

<div class="p-4 min-h-[60vh] flex items-center justify-center">
	<div class="panel max-w-md text-center">
		<div class="text-4xl mb-2">⚠️</div>
		<h1 class="text-xl font-bold mb-2">Something went wrong</h1>
		<p class="text-muted text-sm mb-4">
			{$page.error?.message ?? 'An unexpected error occurred.'}
			{#if $page.status}
				<span class="block text-xs mt-1">status {$page.status}</span>
			{/if}
		</p>
		<div class="flex gap-2 justify-center">
			<button class="btn" onclick={() => location.reload()}>Retry</button>
			<a class="btn" href={base + '/'}>Back to board</a>
		</div>
	</div>
</div>
