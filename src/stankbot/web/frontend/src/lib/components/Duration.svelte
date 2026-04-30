<script lang="ts">
	import { formatDurationMs } from '$lib/format';
	import { formatDateTime } from '$lib/datetime';
	import Tooltip from '$lib/components/Tooltip.svelte';

	interface Props {
		start?: string | null;
		end?: string | null;
		class?: string;
	}

	let { start, end, class: className = '' }: Props = $props();

	let now = $state(Date.now());

	let live = $derived(!start || !end);

	let startTs = $derived(start ? new Date(start).getTime() : now);
	let endTs = $derived(end ? new Date(end).getTime() : now);
	let diffMs = $derived(Math.abs(endTs - startTs));

	let formatted = $derived(formatDurationMs(diffMs));

	$effect(() => {
		if (!live) return;
		now = Date.now();
		const interval = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(interval);
	});
</script>

{#if formatted}
	<Tooltip>
		<span class="tabular-nums cursor-help {className}">{formatted}</span>
		{#snippet tooltip()}
			{#if start && end}
				<div class="flex flex-col gap-0.5">
					<div class="flex gap-2"><span class="w-12 shrink-0 text-right text-muted">Start</span><span>{formatDateTime(start)}</span></div>
					<div class="flex gap-2"><span class="w-12 shrink-0 text-right text-muted">End</span><span>{formatDateTime(end)}</span></div>
				</div>
			{:else if start}
				{formatDateTime(start)}
			{:else if end}
				{formatDateTime(end)}
			{/if}
		{/snippet}
	</Tooltip>
{/if}
