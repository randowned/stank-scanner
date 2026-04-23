<script lang="ts">
	interface Props {
		checked?: boolean;
		disabled?: boolean;
		label?: string;
		id?: string;
		ariaLabel?: string;
		onchange?: (value: boolean) => void;
	}

	let {
		checked = $bindable(false),
		disabled = false,
		label,
		id,
		ariaLabel,
		onchange
	}: Props = $props();

	function toggle() {
		if (disabled) return;
		checked = !checked;
		onchange?.(checked);
	}
</script>

<label class="inline-flex items-center gap-2 cursor-pointer {disabled ? 'opacity-50 cursor-not-allowed' : ''}">
	<button
		type="button"
		role="switch"
		aria-checked={checked}
		aria-label={ariaLabel ?? label ?? 'Toggle'}
		{disabled}
		{id}
		onclick={toggle}
		class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors {checked ? 'bg-accent' : 'bg-border'}"
	>
		<span
			class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform {checked ? 'translate-x-4' : 'translate-x-0.5'}"
		></span>
	</button>
	{#if label}<span class="text-sm text-text">{label}</span>{/if}
</label>
