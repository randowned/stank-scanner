<script lang="ts">
	interface Props {
		value?: string | number;
		type?: 'text' | 'number' | 'email' | 'password' | 'url' | 'search';
		placeholder?: string;
		disabled?: boolean;
		readonly?: boolean;
		name?: string;
		id?: string;
		min?: number;
		max?: number;
		step?: number;
		autocomplete?: HTMLInputElement['autocomplete'];
		class?: string;
		oninput?: (e: Event) => void;
		onchange?: (e: Event) => void;
	}

	let {
		value = $bindable(''),
		type = 'text',
		placeholder,
		disabled = false,
		readonly = false,
		name,
		id,
		min,
		max,
		step,
		autocomplete,
		class: klass = '',
		oninput,
		onchange
	}: Props = $props();
</script>

{#if type === 'number'}
	<input
		type="number"
		bind:value
		{placeholder}
		{disabled}
		{readonly}
		{name}
		{id}
		{min}
		{max}
		{step}
		{autocomplete}
		class="input {klass}"
		{oninput}
		{onchange}
	/>
{:else}
	<input
		{type}
		bind:value
		{placeholder}
		{disabled}
		{readonly}
		{name}
		{id}
		{autocomplete}
		class="input {klass}"
		{oninput}
		{onchange}
	/>
{/if}
