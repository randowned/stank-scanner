<script lang="ts">
	interface MilestoneEntry {
		id: number;
		mediaItemId: number;
		title: string;
		metricKey: string;
		milestoneValue: number;
		newValue: number;
		thumbnailUrl?: string | null;
		name?: string | null;
	}

	let { entries = $bindable() }: { entries: MilestoneEntry[] } = $props();

	function dismiss(id: number) {
		entries = entries.filter((e) => e.id !== id);
	}

	function formatMilestone(value: number): string {
		if (value >= 1_000_000_000) return (value / 1_000_000_000).toFixed(1).replace(/\.0$/, '') + 'B';
		if (value >= 1_000_000) return (value / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
		if (value >= 1_000) return (value / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
		return value.toLocaleString('en-US');
	}

	function metricLabel(key: string): string {
		const labels: Record<string, string> = {
			view_count: 'views',
			like_count: 'likes',
			comment_count: 'comments',
			playcount: 'plays'
		};
		return labels[key] ?? key;
	}
</script>

{#if entries.length > 0}
	<div class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm" data-testid="media-milestone-overlay">
		{#each entries.slice(0, 3) as entry (entry.id)}
			<div
				class="panel border-accent/30 flex items-start gap-3 p-3 cursor-pointer animate-slide-up"
				onclick={() => dismiss(entry.id)}
				onkeydown={(e) => { if (e.key === 'Enter') dismiss(entry.id); }}
				role="button"
				tabindex="0"
				data-testid="media-milestone-item"
			>
				{#if entry.thumbnailUrl}
					<img src={entry.thumbnailUrl} alt="" class="w-10 h-10 rounded object-cover shrink-0" />
				{:else}
					<div class="w-10 h-10 rounded bg-border flex items-center justify-center text-lg shrink-0">🏆</div>
				{/if}
				<div class="min-w-0 flex-1">
					<div class="text-sm font-semibold text-text truncate">{entry.title}</div>
					<div class="text-xs text-muted mt-0.5">
						{formatMilestone(entry.milestoneValue)} {metricLabel(entry.metricKey)}
					</div>
				</div>
				<button
					type="button"
					class="text-muted hover:text-text shrink-0 text-lg leading-none"
					onclick={(e) => { e.stopPropagation(); dismiss(entry.id); }}
					aria-label="Dismiss"
				>×</button>
			</div>
		{/each}
	</div>
{/if}

<style>
	@keyframes slideUp {
		from { opacity: 0; transform: translateY(16px); }
		to { opacity: 1; transform: translateY(0); }
	}
	.animate-slide-up {
		animation: slideUp 0.3s ease-out;
	}
</style>
