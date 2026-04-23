<script lang="ts">
	import { apiFetch, apiPost, FetchError } from '$lib/api';
	import { onMount } from 'svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Select from '$lib/components/Select.svelte';
	import Textarea from '$lib/components/Textarea.svelte';
	import Tabs from '$lib/components/Tabs.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';

	interface TemplatesDoc {
		keys: string[];
		templates: Record<string, Record<string, unknown>>;
	}

	const PRESETS = [
		{ value: 'chain_board', label: 'Chain board' },
		{ value: 'chain_record', label: 'Chain record' },
		{ value: 'chain_break', label: 'Chain break' },
		{ value: 'session_start', label: 'Session start' },
		{ value: 'points', label: 'Points' },
		{ value: 'cooldown', label: 'Cooldown' }
	];

	let doc = $state<TemplatesDoc | null>(null);
	let loadError = $state<string | null>(null);

	let activeKey = $state<string>('');
	let jsonText = $state('');
	let saveMsg = $state<string | null>(null);
	let saving = $state(false);
	let preset = $state('chain_board');
	let preview = $state<Record<string, unknown> | null>(null);
	let previewError = $state<string | null>(null);

	let previewTimer: ReturnType<typeof setTimeout> | null = null;

	async function load() {
		try {
			doc = await apiFetch<TemplatesDoc>('/api/admin/templates');
			if (doc.keys.length > 0 && !activeKey) {
				activeKey = doc.keys[0];
			}
			selectKey(activeKey);
		} catch (err) {
			loadError = err instanceof FetchError ? err.message : 'Failed to load templates';
		}
	}

	function selectKey(k: string) {
		if (!doc) return;
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
		previewError = null;
		let parsed: unknown;
		try {
			parsed = JSON.parse(jsonText);
		} catch (err) {
			previewError = `Invalid JSON: ${(err as Error).message}`;
			return;
		}
		try {
			const res = await apiPost<{ rendered: Record<string, unknown> }>(
				`/api/admin/templates/${activeKey}/preview`,
				{ data: parsed, context_preset: preset }
			);
			preview = res.rendered;
		} catch (err) {
			previewError = err instanceof FetchError ? err.message : 'Preview failed';
		}
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
				saveMsg = err instanceof FetchError ? err.message : 'Save failed';
			}
		} finally {
			saving = false;
		}
	}

	const tabs = $derived.by(() =>
		(doc?.keys ?? []).map((k) => ({ value: k, label: k.replace(/_/g, ' ') }))
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
{:else if doc}
	<Tabs {tabs} value={activeKey} onchange={(v) => selectKey(v)} />

	<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
		<Card title="Template JSON">
			<Textarea bind:value={jsonText} rows={22} oninput={schedulePreview} />
			<div class="mt-3 flex items-center gap-2">
				<Button onclick={save} loading={saving}>Save</Button>
				<Button variant="secondary" onclick={runPreview}>Preview</Button>
				{#if saveMsg}<span class="text-sm text-muted">{saveMsg}</span>{/if}
			</div>
		</Card>

		<Card title="Preview">
			<div class="mb-3 flex items-center gap-2">
				<label class="text-sm text-muted">Context:</label>
				<Select
					bind:value={preset}
					options={PRESETS}
					onchange={() => runPreview()}
				/>
			</div>

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
		</Card>
	</div>
{/if}
