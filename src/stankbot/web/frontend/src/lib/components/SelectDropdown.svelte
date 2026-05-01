<script lang="ts" generics="T extends string | number">
	import Dropdown from '$lib/components/Dropdown.svelte';
	import DropdownItem from '$lib/components/DropdownItem.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';

	interface Option {
		value: T;
		label: string;
		icon?: string;
	}

	interface Props {
		value?: T;
		options: Option[];
		disabled?: boolean;
		position?: 'left' | 'right';
		class?: string;
		testId?: string;
	}

	let {
		value = $bindable(),
		options,
		disabled = false,
		position = 'left',
		class: klass = '',
		testId
	}: Props = $props();

	let selected = $derived(options.find((o) => o.value === value));
	let selectedIcon = $derived(selected?.icon ?? '');
	let selectedLabel = $derived(selected?.label ?? '');
</script>

<Tooltip side="above">
	<Dropdown align={position}>
		{#snippet trigger({ toggle, open })}
			<button
				type="button"
				class="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border bg-panel hover:bg-border/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed {klass}"
				{disabled}
				onclick={toggle}
				data-testid={testId}
				aria-expanded={open}
				aria-label={selectedLabel}
			>
				<span class="text-base leading-none">{selectedIcon}</span>
				<span class="text-muted text-[8px] leading-none ml-0.5">{open ? '▲' : '▼'}</span>
			</button>
		{/snippet}
		{#each options as opt (opt.value)}
			<DropdownItem
				active={opt.value === value}
				keepOpen={false}
				onclick={() => { value = opt.value; }}
			>
				{#if opt.icon}
					<span class="text-base">{opt.icon}</span>
				{/if}
				{opt.label}
			</DropdownItem>
		{/each}
	</Dropdown>
	{#snippet tooltip()}
		{selectedLabel}
	{/snippet}
</Tooltip>
