<script lang="ts">
	import { formatDateTime } from '$lib/datetime';
	import { formatRelativeTime, formatRelativeTimeShort } from '$lib/format';
	import Tooltip from '$lib/components/Tooltip.svelte';

	interface Props {
		datetime: string | null | undefined;
		short?: boolean;
		fallback?: string;
		class?: string;
		testId?: string;
	}

	let { datetime, short = false, fallback = '—', class: klass = '', testId }: Props = $props();

	let display = $derived(datetime ? (short ? formatRelativeTimeShort(datetime) : formatRelativeTime(datetime)) : fallback);
	let tooltipText = $derived(datetime ? formatDateTime(datetime) : '');
	let nativeTitle = $derived(datetime ? formatDateTime(datetime) : '');
</script>

{#if datetime}
	{#if testId}
		<span data-testid={testId} class="inline-flex">
			<Tooltip>
				<span class="tabular-nums cursor-help {klass}" title={nativeTitle}>{display}</span>
				{#snippet tooltip()}
					{tooltipText}
				{/snippet}
			</Tooltip>
		</span>
	{:else}
		<Tooltip>
			<span class="tabular-nums cursor-help {klass}" title={nativeTitle}>{display}</span>
			{#snippet tooltip()}
				{tooltipText}
			{/snippet}
		</Tooltip>
	{/if}
{:else}
	<span class="{klass}">{fallback}</span>
{/if}
