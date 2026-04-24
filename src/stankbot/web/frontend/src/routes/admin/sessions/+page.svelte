<script lang="ts">
	import { apiPost, FetchError } from '$lib/api';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Input from '$lib/components/Input.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	let newSessionOpen = $state(false);
	let resetOpen = $state(false);
	let rebuildOpen = $state(false);
	let resetTyped = $state('');
	let opsMsg = $state<string | null>(null);
	let opsBusy = $state(false);

	async function runNewSession() {
		opsBusy = true;
		opsMsg = null;
		try {
			const res = await apiPost<{ new_session_id: number }>('/api/admin/new-session');
			opsMsg = `Started session ${res.new_session_id}.`;
		} catch (err) {
			opsMsg = err instanceof FetchError ? err.message : 'Failed';
		} finally {
			opsBusy = false;
		}
	}

	async function runReset() {
		opsBusy = true;
		opsMsg = null;
		try {
			await apiPost('/api/admin/reset', { confirm: 'RESET' });
			opsMsg = 'Guild state reset.';
			resetTyped = '';
		} catch (err) {
			opsMsg = err instanceof FetchError ? err.message : 'Reset failed';
		} finally {
			opsBusy = false;
		}
	}

	async function runRebuild() {
		opsBusy = true;
		opsMsg = null;
		try {
			const res = await apiPost<Record<string, unknown>>('/api/admin/rebuild');
			opsMsg = `Rebuild complete. ${JSON.stringify(res)}`;
		} catch (err) {
			opsMsg = err instanceof FetchError ? err.message : 'Rebuild failed';
		} finally {
			opsBusy = false;
		}
	}
</script>

<PageHeader title="Sessions" subtitle="Session lifecycle and state operations" />

<div class="max-w-lg space-y-4">
	<Card title="Start new session">
		<p class="text-sm text-muted mb-3">Ends the current session immediately and starts a fresh one.</p>
		<div class="flex justify-end">
			<Button onclick={() => (newSessionOpen = true)} loading={opsBusy}>Start new session</Button>
		</div>
	</Card>

	<Card title="Rebuild state">
		<p class="text-sm text-muted mb-3">
			Replay the event log to recompute totals, chains, and records. May take a while on large guilds.
		</p>
		<div class="flex justify-end">
			<Button variant="danger" onclick={() => (rebuildOpen = true)} loading={opsBusy}>Rebuild</Button>
		</div>
	</Card>

	<Card title="Reset everything">
		<p class="text-sm text-muted mb-3">
			Deletes all events, chains, cooldowns, records, achievements, and totals. <strong>Irreversible.</strong>
		</p>
		<div class="mb-3">
			<label for="reset-typed" class="text-xs text-muted block mb-1">Type RESET to enable</label>
			<Input id="reset-typed" bind:value={resetTyped} placeholder="RESET" />
		</div>
		<div class="flex justify-end">
			<Button
				variant="danger"
				disabled={resetTyped !== 'RESET' || opsBusy}
				onclick={() => (resetOpen = true)}
			>Reset everything</Button>
		</div>
	</Card>

	{#if opsMsg}
		<p class="text-sm text-muted break-all">{opsMsg}</p>
	{/if}
</div>

<ConfirmDialog
	bind:open={newSessionOpen}
	title="End current session?"
	body="This ends the current session immediately and starts a new one."
	confirmLabel="Start new session"
	onconfirm={runNewSession}
/>
<ConfirmDialog
	bind:open={resetOpen}
	title="Irreversible: reset guild state?"
	body="Deletes events, chains, cooldowns, records, achievements, and totals. Not undoable."
	confirmLabel="Reset"
	danger
	onconfirm={runReset}
/>
<ConfirmDialog
	bind:open={rebuildOpen}
	title="Rebuild state?"
	body="Re-derives chains, totals, and records from the event log. May take a while on large guilds."
	confirmLabel="Rebuild"
	danger
	onconfirm={runRebuild}
/>
