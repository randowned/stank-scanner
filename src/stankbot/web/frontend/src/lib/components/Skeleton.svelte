<script lang="ts">
	interface Props {
		width?: string;
		height?: string;
		rounded?: 'sm' | 'md' | 'lg' | 'full';
		class?: string;
	}

	let { width = '100%', height = '1rem', rounded = 'md', class: klass = '' }: Props = $props();

	const roundedCls: Record<string, string> = {
		sm: 'rounded-sm',
		md: 'rounded-md',
		lg: 'rounded-lg',
		full: 'rounded-full'
	};
</script>

<div
	class="bg-border/60 animate-pulse {roundedCls[rounded]} {klass}"
	style="width: {width}; height: {height};"
	aria-hidden="true"
></div>
