<script lang="ts">
	import { formatDurationMs } from '$lib/format';
	import { formatDateTime } from '$lib/datetime';
	import Tooltip from '$lib/components/Tooltip.svelte';

	interface Props {
		start?: string | null;
		end?: string | null;
		useNativeTooltip?: boolean;
		class?: string;
	}

	let { start, end, useNativeTooltip = false, class: className = '' }: Props = $props();

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

	let nativeTitle = $derived.by(() => {
		if (start && end) return `Start: ${formatDateTime(start)} · End: ${formatDateTime(end)}`;
		if (start) return formatDateTime(start);
		if (end) return formatDateTime(end);
		return '';
	});
</script>

{#if formatted}
	{#if useNativeTooltip}
		<span class="tabular-nums {className}" title={nativeTitle}>{formatted}</span>
	{:else}
		<Tooltip>
			<span class="tabular-nums cursor-help {className}">{formatted}</span>
			{#snippet tooltip()}
				{#if start && end}
					<div class="flex gap-2">
						<div class="flex flex-col items-end gap-2"><span class="text-right text-muted">Start</span><span class="text-right text-muted">End</span></div>
						<div class="flex flex-col items-start gap-2"><span>{formatDateTime(start)}</span><span>{formatDateTime(end)}</span></div>
					</div>
				{:else if start}
					{formatDateTime(start)}
				{:else if end}
					{formatDateTime(end)}
				{/if}
			{/snippet}
		</Tooltip>
	{/if}
{/if}
