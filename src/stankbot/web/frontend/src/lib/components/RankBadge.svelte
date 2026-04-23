<script lang="ts">
	interface Props {
		rank: number;
	}

	let { rank }: Props = $props();

	const variant = $derived(
		rank === 1
			? 'bg-gold text-bg'
			: rank === 2
				? 'bg-gray-300 text-bg'
				: rank === 3
					? 'bg-amber-600 text-white'
					: 'bg-border text-muted'
	);
</script>

<div
	class="w-8 h-8 flex items-center justify-center rounded-full text-sm font-bold {variant}"
	aria-label="Rank {rank}"
>
	{rank}
</div>
