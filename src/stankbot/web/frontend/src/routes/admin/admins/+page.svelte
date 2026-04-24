<script lang="ts">
	import { apiFetch, apiPost, FetchError } from '$lib/api';
	import { onMount } from 'svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Input from '$lib/components/Input.svelte';
	import FormField from '$lib/components/FormField.svelte';

	interface RolesDoc {
		role_ids: string[];
		role_names: Record<string, string>;
		global_user_ids: string[];
		names: Record<string, string>;
	}

	let doc = $state<RolesDoc | null>(null);
	let error = $state<string | null>(null);
	let newRole = $state('');
	let newUser = $state('');

	async function load() {
		try {
			doc = await apiFetch<RolesDoc>('/api/admin/roles');
		} catch (err) {
			error = err instanceof FetchError ? err.message : 'Failed to load';
		}
	}

	async function addRole() {
		if (!newRole.trim()) return;
		error = null;
		try {
			await apiPost('/api/admin/roles/add', { role_id: Number(newRole) });
			newRole = '';
			await load();
		} catch (err) {
			error = err instanceof FetchError ? err.message : 'Add failed';
		}
	}

	async function removeRole(role: string) {
		error = null;
		try {
			await apiPost('/api/admin/roles/remove', { role_id: Number(role) });
			await load();
		} catch (err) {
			error = err instanceof FetchError ? err.message : 'Remove failed';
		}
	}

	async function addUser() {
		if (!newUser.trim()) return;
		error = null;
		try {
			await apiPost('/api/admin/roles/users/add', { user_id: Number(newUser) });
			newUser = '';
			await load();
		} catch (err) {
			error = err instanceof FetchError ? err.message : 'Add failed';
		}
	}

	async function removeUser(uid: string) {
		error = null;
		try {
			await apiPost('/api/admin/roles/users/remove', { user_id: Number(uid) });
			await load();
		} catch (err) {
			error = err instanceof FetchError ? err.message : 'Remove failed';
		}
	}

	onMount(load);
</script>

<PageHeader title="Admins" subtitle="Per-guild admin roles and global admin users" />

{#if error}<div class="text-sm text-danger mb-3">{error}</div>{/if}

<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
	<Card title="Guild admin roles">
		{#if doc}
			<ul class="mb-4 space-y-1">
				{#each doc.role_ids as r (r)}
					<li class="flex items-center justify-between text-sm">
						<span>
							{#if doc.role_names[r]}
								<span class="font-medium">{doc.role_names[r]}</span>
								<span class="text-muted font-mono ml-1">#{r}</span>
							{:else}
								<span class="font-mono">{r}</span>
							{/if}
						</span>
						<button class="text-danger text-sm" onclick={() => removeRole(r)}>Remove</button>
					</li>
				{:else}
					<li class="text-muted text-sm">No roles configured.</li>
				{/each}
			</ul>
		{/if}
		<FormField label="Add role ID">
			<Input bind:value={newRole} type="number" placeholder="Discord role ID" />
		</FormField>
		<div class="flex justify-end mt-2">
			<Button onclick={addRole}>Add</Button>
		</div>
	</Card>

	<Card title="Global admin users">
		{#if doc}
			<ul class="mb-4 space-y-1">
				{#each doc.global_user_ids as u (u)}
					<li class="flex items-center justify-between text-sm">
						<span>
							{#if doc.names[u]}
								<span class="font-medium">{doc.names[u]}</span>
								<span class="text-muted font-mono ml-1">#{u}</span>
							{:else}
								<span class="font-mono">{u}</span>
							{/if}
						</span>
						<button class="text-danger text-sm" onclick={() => removeUser(u)}>Remove</button>
					</li>
				{:else}
					<li class="text-muted text-sm">No global admins.</li>
				{/each}
			</ul>
		{/if}
		<FormField label="Add user ID">
			<Input bind:value={newUser} type="number" placeholder="Discord user ID" />
		</FormField>
		<div class="flex justify-end mt-2">
			<Button onclick={addUser}>Add</Button>
		</div>
	</Card>
</div>
