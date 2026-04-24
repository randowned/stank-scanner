<script lang="ts">
	interface Props {
		value?: string;
		placeholder?: string;
		rows?: number;
		disabled?: boolean;
		readonly?: boolean;
		name?: string;
		id?: string;
		class?: string;
		oninput?: (e: Event) => void;
		onchange?: (e: Event) => void;
		testId?: string;
	}

	let {
		value = $bindable(''),
		placeholder,
		rows = 4,
		disabled = false,
		readonly = false,
		name,
		id,
		class: klass = '',
		oninput,
		onchange,
		testId
	}: Props = $props();
</script>

<textarea
	bind:value
	{placeholder}
	{rows}
	{disabled}
	{readonly}
	{name}
	{id}
	class="input font-mono text-sm {klass}"
	{oninput}
	{onchange}
	data-testid={testId}
></textarea>
