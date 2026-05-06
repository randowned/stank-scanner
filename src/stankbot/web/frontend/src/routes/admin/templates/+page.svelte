<script lang="ts">
	import { apiFetch, apiPost } from '$lib/api';
import { toErrorMessage } from '$lib/api-utils';
	import { onMount } from 'svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Select from '$lib/components/Select.svelte';
	import Textarea from '$lib/components/Textarea.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';

	interface TemplatesDoc {
		keys: string[];
		templates: Record<string, Record<string, unknown>>;
		defaults: Record<string, Record<string, unknown>>;
	}

	const TEMPLATE_LABELS: Record<string, string> = {
		board_embed: 'Board',
		record_embed: 'Record',
		chain_break_embed: 'Chain break',
		new_session_embed: 'New session',
		cooldown_embed: 'Cooldown',
		points_embed: 'Points',
		youtube_media_embed: 'YouTube Media',
		spotify_media_embed: 'Spotify Media',
		youtube_milestone_embed: 'YouTube Milestone',
		spotify_milestone_embed: 'Spotify Milestone'
	};

	const KEY_TO_PRESET: Record<string, string> = {
		board_embed: 'chain_board',
		record_embed: 'chain_record',
		chain_break_embed: 'chain_break',
		new_session_embed: 'session_start',
		cooldown_embed: 'cooldown',
		points_embed: 'points',
		youtube_milestone_embed: 'youtube_milestone',
		spotify_milestone_embed: 'spotify_milestone'
	};

	let doc = $state<TemplatesDoc | null>(null);
	let loadError = $state<string | null>(null);

	let activeKey = $state<string>('');
	let jsonText = $state('');
	let saveMsg = $state<string | null>(null);
	let saving = $state(false);
	let preview = $state<Record<string, unknown> | null>(null);
	let previewError = $state<string | null>(null);
	let activeTab = $state<'preview' | 'edit'>('preview');

	let previewTimer: ReturnType<typeof setTimeout> | null = null;

	async function load() {
		try {
			doc = await apiFetch<TemplatesDoc>('/api/admin/templates');
			if (doc.keys.length > 0 && !activeKey) {
				activeKey = doc.keys[0];
			}
			selectKey(activeKey);
		} catch (err) {
			loadError = toErrorMessage(err, 'Failed to load templates');
		}
	}

	function selectKey(k: string) {
		if (!doc || !k) return;
		activeKey = k;
		const tmpl = doc.templates[k] ?? {};
		jsonText = JSON.stringify(tmpl, null, 2);
		schedulePreview();
	}

	function schedulePreview() {
		if (previewTimer) clearTimeout(previewTimer);
		previewTimer = setTimeout(runPreview, 250);
	}

	async function runPreview() {
		if (!activeKey) return;
		previewError = null;
		let parsed: unknown;
		try {
			parsed = JSON.parse(jsonText);
		} catch (err) {
			previewError = `Invalid JSON: ${(err as Error).message}`;
			return;
		}
		try {
			const preset = KEY_TO_PRESET[activeKey] ?? 'chain_board';
			const res = await apiPost<{ rendered: Record<string, unknown> }>(
				`/api/admin/templates/${activeKey}/preview`,
				{ data: parsed, context_preset: preset }
			);
			preview = res.rendered;
		} catch (err) {
			previewError = toErrorMessage(err, 'Preview failed');
		}
	}

	function resetToSaved() {
		if (!doc) return;
		const tmpl = doc.templates[activeKey] ?? {};
		jsonText = JSON.stringify(tmpl, null, 2);
		saveMsg = null;
		schedulePreview();
	}

	function resetToDefault() {
		if (!doc) return;
		const tmpl = doc.defaults[activeKey] ?? {};
		jsonText = JSON.stringify(tmpl, null, 2);
		saveMsg = null;
		schedulePreview();
	}

	async function save() {
		saveMsg = null;
		saving = true;
		try {
			const parsed = JSON.parse(jsonText);
			await apiPost(`/api/admin/templates/${activeKey}`, { data: parsed });
			saveMsg = 'Saved.';
			await load();
		} catch (err) {
			if (err instanceof SyntaxError) {
				saveMsg = `Invalid JSON: ${err.message}`;
			} else {
				saveMsg = toErrorMessage(err, 'Save failed');
			}
		} finally {
			saving = false;
		}
	}

	const templateOptions = $derived.by(() =>
		(doc?.keys ?? []).map((k) => ({ value: k, label: TEMPLATE_LABELS[k] ?? k.replace(/_/g, ' ') }))
	);

	const previewFields = $derived.by(() => {
		if (!preview) return [];
		const f = (preview as { fields?: unknown[] }).fields;
		return Array.isArray(f) ? f : [];
	});

	onMount(load);
</script>

<PageHeader title="Templates" subtitle="Edit the bot's embed templates with live preview" />

{#if loadError}
	<ErrorState message={loadError} onretry={load} />
{:else if !doc}
	<div class="mb-4">
		<div class="h-9 bg-border/60 animate-pulse rounded-md w-64 mb-4"></div>
	</div>
	<div class="panel">
		<div class="flex gap-1 border border-border rounded-md overflow-hidden w-40 mb-4">
			<div class="h-8 bg-border/60 animate-pulse rounded w-20"></div>
			<div class="h-8 bg-border/60 animate-pulse rounded w-20"></div>
		</div>
		<div class="h-96 bg-border/60 animate-pulse rounded-md"></div>
		<div class="mt-3 flex items-center justify-between gap-3">
			<div class="flex gap-2">
				<div class="h-9 w-16 bg-border/60 animate-pulse rounded-md"></div>
				<div class="h-9 w-20 bg-border/60 animate-pulse rounded-md"></div>
			</div>
			<div class="h-9 w-16 bg-border/60 animate-pulse rounded-md"></div>
		</div>
	</div>
{:else if doc}
	<div class="mb-4 flex items-center gap-3">
		<label for="template-select" class="text-sm text-muted shrink-0">Template:</label>
		<Select
			bind:value={activeKey}
			options={templateOptions}
			onchange={(e) => selectKey((e.target as HTMLSelectElement).value)}
			id="template-select"
			testId="template-select"
		/>
	</div>

	<Card>
		<div class="flex items-center mb-4">
			<div class="flex gap-1 border border-border rounded-md overflow-hidden">
				<button
					type="button"
					class="px-3 py-1.5 text-sm transition-colors {activeTab === 'preview' ? 'bg-accent text-[#1a1425]' : 'text-muted hover:text-text'}"
					onclick={() => { activeTab = 'preview'; runPreview(); }}
					data-testid="tab-preview"
				>Preview</button>
				<button
					type="button"
					class="px-3 py-1.5 text-sm transition-colors {activeTab === 'edit' ? 'bg-accent text-[#1a1425]' : 'text-muted hover:text-text'}"
					onclick={() => { activeTab = 'edit'; }}
					data-testid="tab-edit"
				>Edit</button>
			</div>
		</div>

		{#if activeTab === 'preview'}
			{#if previewError}
				<p class="text-sm text-danger">{previewError}</p>
			{:else if preview}
				<div
					class="rounded-md border-l-4 border-accent bg-bg/60 p-3 text-sm"
					data-testid="template-preview"
				>
					{#if typeof preview.title === 'string'}
						<div class="font-semibold">{preview.title}</div>
					{/if}
					{#if typeof preview.description === 'string'}
						<div class="mt-1 whitespace-pre-wrap">{preview.description}</div>
					{/if}
					{#if previewFields.length > 0}
						<div class="mt-3 grid grid-cols-2 gap-2">
							{#each previewFields as f, i (i)}
								<div class={(f as { inline?: boolean }).inline ? '' : 'col-span-2'}>
									<div class="text-xs font-semibold">{(f as { name?: string }).name ?? ''}</div>
									<div class="text-xs text-muted whitespace-pre-wrap">
										{(f as { value?: string }).value ?? ''}
									</div>
								</div>
							{/each}
						</div>
					{/if}
					{#if typeof preview.footer === 'string' && preview.footer}
						<div class="mt-3 text-xs text-muted">{preview.footer}</div>
					{/if}
				</div>
			{/if}
		{:else}
			<Textarea bind:value={jsonText} rows={22} oninput={schedulePreview} testId="template-json" />
			<div class="mt-3 flex items-center justify-between gap-3">
				<div class="flex gap-2">
					<Button variant="secondary" onclick={resetToSaved} testId="template-reset">Reset</Button>
					<Button variant="secondary" onclick={resetToDefault} testId="template-default">Default</Button>
				</div>
				<div class="flex items-center gap-3">
					{#if saveMsg}<span class="text-sm text-muted" data-testid="template-save-msg">{saveMsg}</span>{/if}
					<Button onclick={save} loading={saving} testId="template-save">Save</Button>
				</div>
			</div>
		{/if}
	</Card>
{/if}
