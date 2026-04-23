<script lang="ts" generics="T extends string">
	interface Tab {
		value: T;
		label: string;
		badge?: string | number;
	}

	interface Props {
		tabs: Tab[];
		value?: T;
		onchange?: (value: T) => void;
	}

	let { tabs, value = $bindable(), onchange }: Props = $props();

	function select(v: T) {
		value = v;
		onchange?.(v);
	}
</script>

<div class="flex gap-1 border-b border-border mb-4 overflow-x-auto scrollbar-thin" role="tablist">
	{#each tabs as tab (tab.value)}
		<button
			type="button"
			role="tab"
			aria-selected={value === tab.value}
			onclick={() => select(tab.value)}
			class="px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors {value === tab.value ? 'border-accent text-text' : 'border-transparent text-muted hover:text-text'}"
		>
			{tab.label}
			{#if tab.badge !== undefined}
				<span class="ml-1 text-xs text-muted">({tab.badge})</span>
			{/if}
		</button>
	{/each}
</div>
