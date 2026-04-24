<script lang="ts" generics="T extends string | number">
	interface Option {
		value: T;
		label: string;
	}

	interface Props {
		value?: T;
		options: Option[];
		disabled?: boolean;
		name?: string;
		id?: string;
		class?: string;
		onchange?: (e: Event) => void;
		testId?: string;
	}

	let {
		value = $bindable(),
		options,
		disabled = false,
		name,
		id,
		class: klass = '',
		onchange,
		testId
	}: Props = $props();
</script>

<select bind:value {disabled} {name} {id} class="input {klass}" {onchange} data-testid={testId}>
	{#each options as opt (opt.value)}
		<option value={opt.value}>{opt.label}</option>
	{/each}
</select>
