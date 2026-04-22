<script lang="ts">
	import { base } from '$app/paths';
	import type { SessionSummary } from '../../app.d';

	let { data } = $props();

	const sessions = $derived(data.sessions as SessionSummary[]);

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '—';
		return new Date(dateStr).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			timeZone: 'UTC'
		});
	}
</script>

<div class="p-4 space-y-4">
	<div class="panel">
		<h1 class="text-xl font-bold flex items-center gap-2">
			<span>📜</span>
			<span>Session History</span>
		</h1>
	</div>

	{#if !sessions.length}
		<div class="panel">
			<p class="text-muted text-center py-8">No sessions recorded yet.</p>
		</div>
	{:else}
		<div class="space-y-2">
			{#each sessions as session}
				<a href="{base}/session/{session.session_id}" class="panel flex items-center justify-between">
					<div>
						<div class="font-medium">Session #{session.session_id}</div>
						<div class="text-xs text-muted">
							{formatDate(session.started_at)}
						</div>
					</div>
					<div class="text-right text-sm">
						<div>{session.chains_started} started</div>
						<div>{session.chains_broken} broken</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}

	<a href={base} class="btn btn-secondary w-full text-center">← Back to Board</a>
</div>