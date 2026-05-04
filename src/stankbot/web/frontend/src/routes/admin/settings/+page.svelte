<script lang="ts">
	import { apiFetch, apiPost } from '$lib/api';
import { toErrorMessage } from '$lib/api-utils';
	import { onMount } from 'svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import FormField from '$lib/components/FormField.svelte';
	import Input from '$lib/components/Input.svelte';
	import Toggle from '$lib/components/Toggle.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';

	interface SettingsDoc {
		guild_id: string;
		guild_name: string;
		values: Record<string, unknown>;
		labels: Record<string, { title: string; help: string }>;
	}

	const INT_KEYS = [
		'sp_flat',
		'sp_position_bonus',
		'sp_starter_bonus',
		'sp_finish_bonus',
		'sp_reaction',
		'sp_team_player_bonus',
		'pp_break_base',
		'pp_break_per_stank',
		'restank_cooldown_seconds',
		'stank_ranking_rows',
		'board_name_max_len'
	];
	const BEHAVIOR_BOOL_KEYS = ['chain_continues_across_sessions', 'enable_reaction_bonus'];
	const LIST_KEYS = ['reset_hours_utc', 'reset_warning_minutes'];

	let doc = $state<SettingsDoc | null>(null);
	let loadError = $state<string | null>(null);
	let saving = $state(false);
	let saveMsg = $state<string | null>(null);

	let ints = $state<Record<string, string>>({});
	let bools = $state<Record<string, boolean>>({});
	let lists = $state<Record<string, string>>({});

	let maintenanceEnabled = $state(false);
	let maintenanceMsg = $state<string | null>(null);

	async function loadSettings() {
		loadError = null;
		try {
			doc = await apiFetch<SettingsDoc>('/api/admin/settings');
			for (const k of INT_KEYS) ints[k] = String(doc.values[k] ?? '');
			for (const k of BEHAVIOR_BOOL_KEYS) bools[k] = Boolean(doc.values[k]);
			for (const k of LIST_KEYS) {
				const raw = doc.values[k];
				lists[k] = Array.isArray(raw) ? raw.join(', ') : String(raw ?? '');
			}
			maintenanceEnabled = Boolean(doc.values['maintenance_mode']);
		} catch (err) {
			loadError = toErrorMessage(err, 'Failed to load settings');
		}
	}

	async function saveSettings() {
		saving = true;
		saveMsg = null;
		try {
			const values: Record<string, unknown> = {};
			for (const k of INT_KEYS) {
				if (ints[k].trim()) values[k] = Number(ints[k]);
			}
			for (const k of BEHAVIOR_BOOL_KEYS) values[k] = bools[k];
			for (const k of LIST_KEYS) {
				if (lists[k].trim()) values[k] = lists[k];
			}
			await apiPost('/api/admin/settings', { values });
			saveMsg = 'Saved.';
		} catch (err) {
			saveMsg = toErrorMessage(err, 'Save failed');
		} finally {
			saving = false;
		}
	}

	async function toggleMaintenance(val: boolean) {
		try {
			await apiPost('/api/admin/settings', { maintenance_mode: val });
			maintenanceMsg = val ? 'Maintenance mode ON' : 'Maintenance mode OFF';
		} catch (err) {
			maintenanceMsg = toErrorMessage(err, 'Failed');
			maintenanceEnabled = !val;
		}
	}

	onMount(loadSettings);
</script>

<PageHeader title="Settings" subtitle={doc?.guild_name ?? ''} />

{#if loadError}
	<ErrorState message={loadError} onretry={loadSettings} />
{:else if !doc}
	<Card>
		{#each Array(6) as _, i (i)}
			<div class="mb-3"><Skeleton height="1.5rem" /></div>
		{/each}
	</Card>
{:else}
	<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
		<Card title="Maintenance">
			<Toggle
				bind:checked={maintenanceEnabled}
				label="Maintenance mode"
				onchange={toggleMaintenance}
			/>
			{#if maintenanceMsg}<p class="text-sm text-muted mt-3">{maintenanceMsg}</p>{/if}
			<p class="text-sm text-muted mt-4">
				When enabled the bot skips scoring, chain detection, and record updates — messages are
				still read (so the gateway stays healthy) but no state is mutated. Useful during
				migrations.
			</p>
		</Card>

		<Card title="Behavior">
			{#each BEHAVIOR_BOOL_KEYS as k (k)}
				{#if doc.labels[k]}
					<FormField label={doc.labels[k].title} hint={doc.labels[k].help}>
						<Toggle bind:checked={bools[k]} label={doc.labels[k].title} />
					</FormField>
				{/if}
			{/each}
		</Card>

		<Card title="Reset windows">
			{#each LIST_KEYS as k (k)}
				{#if doc.labels[k]}
					<FormField label={doc.labels[k].title} hint="{doc.labels[k].help} (comma-separated)">
						<Input bind:value={lists[k]} placeholder="0, 6, 12, 18" />
					</FormField>
				{/if}
			{/each}
		</Card>

		<Card title="Scoring">
			{#each INT_KEYS as k (k)}
				{#if doc.labels[k]}
					<FormField label={doc.labels[k].title} hint={doc.labels[k].help}>
						<Input type="number" bind:value={ints[k]} />
					</FormField>
				{/if}
			{/each}
		</Card>

	</div>

	<div class="flex items-center justify-end gap-3 mt-4">
		{#if saveMsg}<span class="text-sm text-muted">{saveMsg}</span>{/if}
		<Button onclick={saveSettings} loading={saving}>Save settings</Button>
	</div>
{/if}
