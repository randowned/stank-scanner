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

	let { data } = $props();

	const isBotOwner = $derived(data.is_bot_owner ?? false);

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

	// Spotify OAuth
	let spotifyConnected = $state(false);
	let spotifyConnecting = $state(false);
	let spotifyError = $state<string | null>(null);

	async function loadSpotifyStatus() {
		if (!isBotOwner) return;
		try {
			const res = await apiFetch<{ connected: boolean }>('/api/admin/spotify/status');
			spotifyConnected = res.connected;
		} catch {
			spotifyConnected = false;
		}
	}

	async function connectSpotify() {
		window.location.href = '/auth/spotify/login?redirect_to=/admin/settings';
	}

	async function disconnectSpotify() {
		if (spotifyConnecting) return;
		spotifyConnecting = true;
		spotifyError = null;
		try {
			const res = await apiPost<{ connected: boolean }>('/api/admin/spotify/disconnect');
			spotifyConnected = res.connected;
		} catch (err) {
			spotifyError = toErrorMessage(err, 'Failed to disconnect');
		} finally {
			spotifyConnecting = false;
		}
	}

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

	onMount(() => {
		loadSettings();
		loadSpotifyStatus();
	});
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

		{#if isBotOwner}
			<Card title="Spotify Account">
				<div class="flex items-center justify-between gap-3">
					<div>
						{#if spotifyConnected}
							<p class="text-sm font-medium text-green-600 dark:text-green-400 flex items-center gap-1">
								<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
								Connected
							</p>
						{:else}
							<p class="text-sm font-medium text-muted">
								Not connected
							</p>
						{/if}
						<p class="text-sm text-muted mt-1">
							Connect your personal Spotify account to enable play count tracking for tracks you add.
						</p>
					</div>
					<div class="flex-shrink-0">
						{#if spotifyConnected}
							<Button
								onclick={disconnectSpotify}
								loading={spotifyConnecting}
								variant="secondary"
							>
								Disconnect
							</Button>
						{:else}
							<Button onclick={connectSpotify}>
								Connect Spotify
							</Button>
						{/if}
					</div>
				</div>
				{#if spotifyError}
					<p class="text-sm text-red-500 mt-3">{spotifyError}</p>
				{/if}
			</Card>
		{/if}
	</div>

	<div class="flex items-center justify-end gap-3 mt-4">
		{#if saveMsg}<span class="text-sm text-muted">{saveMsg}</span>{/if}
		<Button onclick={saveSettings} loading={saving}>Save settings</Button>
	</div>
{/if}
