<script lang="ts">
	import { apiFetch, apiPost, FetchError } from '$lib/api';
	import { onMount } from 'svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import FormField from '$lib/components/FormField.svelte';
	import Input from '$lib/components/Input.svelte';
	import Toggle from '$lib/components/Toggle.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';

	interface SettingsDoc {
		guild_id: string;
		guild_name: string;
		values: Record<string, unknown>;
		labels: Record<string, { title: string; help: string }>;
	}

	interface Altar {
		id: number;
		channel_id: string;
		sticker_name_pattern: string;
		reaction_emoji_name: string | null;
		enabled: boolean;
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

	// Altar
	let altar = $state<Altar | null>(null);
	let altarLoaded = $state(false);
	let altarSaving = $state(false);
	let altarMsg = $state<string | null>(null);
	let channelId = $state('');
	let pattern = $state('stank');
	let emoji = $state('');

	// Announcements
	let channelIds = $state<string[]>([]);
	let newChannel = $state('');
	let annError = $state<string | null>(null);

	// Maintenance
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
			loadError = err instanceof FetchError ? err.message : 'Failed to load settings';
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
			saveMsg = err instanceof FetchError ? err.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	async function loadAltar() {
		altarLoaded = false;
		try {
			const res = await apiFetch<{ altar: Altar | null }>('/api/admin/altar');
			altar = res.altar;
			if (altar) {
				channelId = altar.channel_id;
				pattern = altar.sticker_name_pattern;
				emoji = altar.reaction_emoji_name ?? '';
			}
		} catch (err) {
			altarMsg = err instanceof FetchError ? err.message : 'Failed to load';
		} finally {
			altarLoaded = true;
		}
	}

	async function saveAltar() {
		altarSaving = true;
		altarMsg = null;
		try {
			await apiPost('/api/admin/altar/set', {
				channel_id: Number(channelId),
				sticker_pattern: pattern,
				reaction_emoji: emoji || null
			});
			await loadAltar();
			altarMsg = 'Altar saved.';
		} catch (err) {
			altarMsg = err instanceof FetchError ? err.message : 'Save failed';
		} finally {
			altarSaving = false;
		}
	}

	async function removeAltar() {
		if (!confirm('Remove this altar?')) return;
		try {
			await apiPost('/api/admin/altar/remove');
			altar = null;
			channelId = '';
			pattern = 'stank';
			emoji = '';
			altarMsg = 'Altar removed.';
		} catch (err) {
			altarMsg = err instanceof FetchError ? err.message : 'Remove failed';
		}
	}

	async function loadAnnouncements() {
		try {
			const res = await apiFetch<{ channel_ids: string[] }>('/api/admin/announcements');
			channelIds = res.channel_ids;
		} catch (err) {
			annError = err instanceof FetchError ? err.message : 'Failed';
		}
	}

	async function addAnnouncement() {
		if (!newChannel.trim()) return;
		try {
			await apiPost('/api/admin/announcements', { channel_id: Number(newChannel) });
			newChannel = '';
			await loadAnnouncements();
		} catch (err) {
			annError = err instanceof FetchError ? err.message : 'Add failed';
		}
	}

	async function removeAnnouncement(id: string) {
		try {
			await apiPost('/api/admin/announcements/remove', { channel_id: Number(id) });
			await loadAnnouncements();
		} catch (err) {
			annError = err instanceof FetchError ? err.message : 'Remove failed';
		}
	}

	async function toggleMaintenance(val: boolean) {
		try {
			await apiPost('/api/admin/maintenance', { enabled: val });
			maintenanceMsg = val ? 'Maintenance mode ON' : 'Maintenance mode OFF';
		} catch (err) {
			maintenanceMsg = err instanceof FetchError ? err.message : 'Failed';
			maintenanceEnabled = !val;
		}
	}

	onMount(() => {
		loadSettings();
		loadAltar();
		loadAnnouncements();
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
		<Card title="Altar">
			{#if !altarLoaded}
				<p class="text-muted text-sm">Loading…</p>
			{:else if !altar}
				<EmptyState
					icon="🗿"
					title="No altar configured"
					message="Pick a channel the bot should watch for stank sticker posts."
				/>
			{/if}
			<FormField label="Channel ID" required hint="Right-click channel in Discord → Copy Channel ID">
				<Input type="number" bind:value={channelId} placeholder="e.g. 1234567890" />
			</FormField>
			<FormField label="Sticker pattern" hint="Substring match, case-insensitive">
				<Input bind:value={pattern} />
			</FormField>
			<FormField
				label="Reaction emoji"
				hint="Custom emoji like <:stank:12345> or a unicode emoji. Leave blank to skip reactions."
			>
				<Input bind:value={emoji} placeholder="<:stank:1234567890>" />
			</FormField>
			<div class="flex justify-end gap-2 mt-2">
				{#if altar}
					<Button variant="danger" onclick={removeAltar}>Remove</Button>
				{/if}
				<Button onclick={saveAltar} loading={altarSaving}>{altar ? 'Update' : 'Create'}</Button>
			</div>
			{#if altarMsg}<p class="text-sm text-muted mt-3">{altarMsg}</p>{/if}
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

		<Card title="Announcements">
			{#if annError}<p class="text-sm text-danger mb-2">{annError}</p>{/if}
			<ul class="mb-4 space-y-1">
				{#each channelIds as id (id)}
					<li class="flex items-center justify-between text-sm">
						<span class="font-mono">{id}</span>
						<button class="text-danger text-sm" onclick={() => removeAnnouncement(id)}>Remove</button>
					</li>
				{:else}
					<li class="text-muted text-sm">No announcement channels configured.</li>
				{/each}
			</ul>
			<FormField label="Add channel ID">
				<Input bind:value={newChannel} type="number" placeholder="Discord channel ID" />
			</FormField>
			<div class="flex justify-end mt-2">
				<Button onclick={addAnnouncement}>Add</Button>
			</div>
		</Card>

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
	</div>

	<div class="flex items-center justify-end gap-3 mt-4">
		{#if saveMsg}<span class="text-sm text-muted">{saveMsg}</span>{/if}
		<Button onclick={saveSettings} loading={saving}>Save settings</Button>
	</div>
{/if}
