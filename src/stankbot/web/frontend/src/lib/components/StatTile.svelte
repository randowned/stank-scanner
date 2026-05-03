<script lang="ts">
	interface Props {
		value: string;
		label: string;
		color?: string;
		flash?: boolean;
		testId?: string;
		valueTestId?: string;
		title?: string;
		fontSize?: string;
	}

	let { value, label, color = 'text-accent', flash = false, testId, valueTestId, title, fontSize = 'xl' }: Props = $props();
</script>

<div class="text-center cursor-default" {title} data-testid={testId}>
	<div class={`text-{fontSize} font-bold {color} {flash ? 'row-flash' : ''}`} data-testid={valueTestId}>{value}</div>
	<div class="text-xs text-muted uppercase">{label}</div>
</div>
