<script lang="ts">
	import { base } from '$app/paths';
	import type { PlayerRow } from '../../app.d';

	let { row, rank, isCurrentUser = false } = $props<{
		row: PlayerRow;
		rank: number;
		isCurrentUser?: boolean;
	}>();

	function formatNet(sp: number, pp: number): string {
		const net = sp - pp;
		return net >= 0 ? `+${net}` : `${net}`;
	}

</script>

<a
	href="{base}/player/{row.user_id}"
	class="flex items-center gap-3 p-3 -mx-2 rounded-lg transition-colors hover:bg-border/50 {isCurrentUser
		? 'bg-accent/10 border border-accent/30'
		: ''}"
>
	<div
		class="w-8 h-8 flex items-center justify-center rounded-full text-sm font-bold shrink-0
			{rank === 1 ? 'bg-gold text-bg' : ''}
			{rank === 2 ? 'bg-gray-300 text-bg' : ''}
			{rank === 3 ? 'bg-amber-600 text-white' : ''}
			{rank > 3 ? 'bg-border text-muted' : ''}"
	>
		{rank}
	</div>
	<div class="flex-1 min-w-0">
		<div class="font-medium truncate {isCurrentUser ? 'text-accent' : ''}">{row.display_name}</div>
		<div class="text-xs text-muted">
			<span class="text-accent">{row.earned_sp}</span> SP ·
			<span class="text-danger">{row.punishments}</span> PP ·
			<span class="{row.earned_sp - row.punishments >= 0 ? 'text-ok' : 'text-danger'} font-semibold"
				>{formatNet(row.earned_sp, row.punishments)}</span
			>
		</div>
	</div>
	{#if isCurrentUser}
		<span class="badge bg-accent/20 text-accent border border-accent/30">You</span>
	{/if}
</a>