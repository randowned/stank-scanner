<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';

	interface Props {
		delta: number;
		kind: 'stank' | 'reaction' | 'break' | 'finish' | 'other';
		onDone?: () => void;
	}

	let { delta, kind, onDone }: Props = $props();

	const icon = $derived(
		kind === 'stank'
			? '🪝'
			: kind === 'reaction'
				? '👍'
				: kind === 'break'
					? '💀'
					: kind === 'finish'
						? '🏁'
						: '✨'
	);

	const color = $derived(delta > 0 ? 'text-ok' : delta < 0 ? 'text-danger' : 'text-muted');
	const sign = $derived(delta > 0 ? '+' : '');

	onMount(() => {
		const t = window.setTimeout(() => onDone?.(), 1200);
		return () => window.clearTimeout(t);
	});
</script>

<span
	class="points-delta-rise absolute -top-1 right-0 inline-flex items-center gap-1 text-xs font-semibold pointer-events-none {color}"
	transition:fade={{ duration: 200 }}
	aria-hidden="true"
>
	<span>{sign}{delta}</span>
	<span>{icon}</span>
</span>
