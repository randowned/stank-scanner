<script lang="ts">
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { apiFetch, apiPost } from '$lib/api';
	import { toErrorMessage } from '$lib/api-utils';
	import type { ProviderDef } from '$lib/types';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Tabs from '$lib/components/Tabs.svelte';
	import Button from '$lib/components/Button.svelte';
	import Input from '$lib/components/Input.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';

	let providers = $state<ProviderDef[]>([]);
	let loadingProviders = $state(true);
	let activeTab = $state<string>('');
	let url = $state('');
	let slug = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	const tabs = $derived(providers.map((p) => ({ value: p.type, label: `${p.icon} ${p.label}` })));

	async function loadProviders() {
		loadingProviders = true;
		try {
			const res = await apiFetch<{ providers: ProviderDef[] }>('/api/admin/media/providers');
			providers = res.providers;
			if (providers.length > 0 && !activeTab) {
				activeTab = providers[0].type;
			}
		} catch {
			providers = [];
		} finally {
			loadingProviders = false;
		}
	}

	async function handleSubmit() {
		if (!activeTab || !url.trim()) return;
		loading = true;
		error = null;
		try {
			await apiPost('/api/admin/media', {
				media_type: activeTab,
				external_id: url.trim(),
				slug: slug.trim() || undefined
			});
			goto(`${base}/admin/media`);
		} catch (err) {
			error = toErrorMessage(err, 'Failed to add media');
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		loadProviders();
	});
</script>

<PageHeader title="Add media" subtitle="Paste a URL or ID from a supported platform" />

{#if loadingProviders}
	<div class="space-y-3 animate-pulse">
		<Skeleton width="200px" height="32px" />
		<Skeleton width="100%" height="40px" />
	</div>
{:else if providers.length === 0}
	<div class="panel">
		<div class="text-muted">No media providers configured. Set up API keys in your environment.</div>
	</div>
{:else}
	<Tabs tabs={tabs} bind:value={activeTab} />

	{#if activeTab === 'youtube'}
		<div class="panel space-y-4">
			<div>
				<label class="block text-sm font-medium mb-1" for="media-add-url">YouTube URL or video ID</label>
				<Input
					type="text"
					id="media-add-url"
					placeholder="https://www.youtube.com/watch?v=... or dQw4w9WgXcQ"
					bind:value={url}
					disabled={loading}
				/>
				<div class="text-xs text-muted mt-1">Paste a full YouTube URL or just the video ID (11 characters).</div>
			</div>
			<div>
				<label class="block text-sm font-medium mb-1" for="media-add-slug">Slug (optional)</label>
				<Input
					type="text"
					id="media-add-slug"
					placeholder="my-cool-video"
					bind:value={slug}
					disabled={loading}
				/>
				<div class="text-xs text-muted mt-1">Short name for Discord commands: <code>/media youtube my-cool-video</code>. Auto-generated if left empty.</div>
			</div>
			{#if error}
				<div class="text-red-400 text-sm">{error}</div>
			{/if}
			<div class="flex justify-end gap-2">
				<a href="{base}/admin/media" class="no-underline">
					<Button variant="secondary" testId="media-add-cancel">Cancel</Button>
				</a>
				<Button variant="primary" onclick={handleSubmit} loading={loading} disabled={!url.trim()} testId="media-add-submit">
					Add video
				</Button>
			</div>
		</div>
	{:else if activeTab === 'spotify'}
		<div class="panel space-y-4">
			<div>
				<label class="block text-sm font-medium mb-1" for="media-add-spotify-url">Spotify track or album URL/URI</label>
				<Input
					type="text"
					id="media-add-spotify-url"
					placeholder="https://open.spotify.com/track/... or spotify:track:..."
					bind:value={url}
					disabled={loading}
				/>
				<div class="text-xs text-muted mt-1">Paste a Spotify URL or URI for a track or album.</div>
			</div>
			<div>
				<label class="block text-sm font-medium mb-1" for="media-add-slug-spotify">Slug (optional)</label>
				<Input
					type="text"
					id="media-add-slug-spotify"
					placeholder="my-cool-track"
					bind:value={slug}
					disabled={loading}
				/>
				<div class="text-xs text-muted mt-1">Short name for Discord commands: <code>/media spotify my-cool-track</code>. Auto-generated if left empty.</div>
			</div>
			{#if error}
				<div class="text-red-400 text-sm">{error}</div>
			{/if}
			<div class="flex justify-end gap-2">
				<a href="{base}/admin/media" class="no-underline">
					<Button variant="secondary" testId="media-add-cancel">Cancel</Button>
				</a>
				<Button variant="primary" onclick={handleSubmit} loading={loading} disabled={!url.trim()} testId="media-add-submit">
					Add to media
				</Button>
			</div>
		</div>
	{/if}
{/if}
