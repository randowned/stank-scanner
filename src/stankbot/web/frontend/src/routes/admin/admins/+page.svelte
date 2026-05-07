<script lang="ts">
	import { apiFetch, apiPost } from '$lib/api';
	import { toErrorMessage } from '$lib/api-utils';
	import { onMount } from 'svelte';
	import { tick } from 'svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import Input from '$lib/components/Input.svelte';
	import FormField from '$lib/components/FormField.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Avatar from '$lib/components/Avatar.svelte';
	import ErrorState from '$lib/components/ErrorState.svelte';

	interface RolesDoc {
		role_ids: string[];
		role_names: Record<string, string>;
		global_user_ids: string[];
		names: Record<string, string>;
		avatars: Record<string, string>;
	}

	let doc = $state<RolesDoc | null>(null);
	let error = $state<string | null>(null);

	let showAddUser = $state(false);
	let showAddRole = $state(false);
	let newUserInput = $state('');
	let newRoleInput = $state('');

	let addingUser = $state(false);
	let addingRole = $state(false);

	async function load() {
		try {
			doc = await apiFetch<RolesDoc>('/api/admin/roles');
		} catch (err) {
			error = toErrorMessage(err, 'Failed to load');
		}
	}

	async function removeUser(uid: string) {
		error = null;
		try {
			await apiPost('/api/admin/roles/users/remove', { user_id: Number(uid) });
			await load();
		} catch (err) {
			error = toErrorMessage(err, 'Remove failed');
		}
	}

	async function removeRole(role: string) {
		error = null;
		try {
			await apiPost('/api/admin/roles/remove', { role_id: Number(role) });
			await load();
		} catch (err) {
			error = toErrorMessage(err, 'Remove failed');
		}
	}

	async function handleAddUser() {
		const trimmed = newUserInput.trim();
		if (!trimmed) return;
		addingUser = true;
		error = null;
		try {
			await apiPost('/api/admin/roles/users/add', { user_id: parseInt(trimmed, 10) });
			newUserInput = '';
			showAddUser = false;
			await load();
		} catch (err) {
			error = toErrorMessage(err, 'Add failed');
		} finally {
			addingUser = false;
		}
	}

	async function handleAddRole() {
		const trimmed = newRoleInput.trim();
		if (!trimmed) return;
		addingRole = true;
		error = null;
		try {
			await apiPost('/api/admin/roles/add', { role_id: Number(trimmed) });
			newRoleInput = '';
			showAddRole = false;
			await load();
		} catch (err) {
			error = toErrorMessage(err, 'Add failed');
		} finally {
			addingRole = false;
		}
	}

	function openAddUser() {
		error = null;
		newUserInput = '';
		showAddUser = true;
	}

	function openAddRole() {
		error = null;
		newRoleInput = '';
		showAddRole = true;
	}

	let addUserBtnEl: HTMLButtonElement;
	let addRoleBtnEl: HTMLButtonElement;

	$effect(() => {
		const _showAddUser = () => { error = null; newUserInput = ''; showAddUser = true; };
		const _showAddRole = () => { error = null; newRoleInput = ''; showAddRole = true; };
		if (addUserBtnEl) addUserBtnEl.addEventListener('click', _showAddUser);
		if (addRoleBtnEl) addRoleBtnEl.addEventListener('click', _showAddRole);
	});

	onMount(load);
</script>

<PageHeader title="Admins" subtitle="Per-guild admin roles and global admin users" />

{#if error}
	<ErrorState message={error} onretry={load} />
{/if}

<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
	<!-- Guild Admin Roles -->
	<Card title="Guild admin roles">
		{#if doc}
			{#if doc.role_ids.length === 0}
				<div class="text-muted text-sm py-2" data-testid="roles-empty">No admin roles configured.</div>
			{:else}
				<ul class="divide-y divide-border" data-testid="roles-list">
					{#each doc.role_ids as r (r)}
						<li class="flex items-center justify-between py-2">
							<div class="min-w-0 flex-1">
								{#if doc.role_names[r]}
									<div class="text-sm font-medium">{doc.role_names[r]}</div>
									<div class="text-xs text-muted font-mono">#{r}</div>
								{:else}
									<div class="text-sm font-mono">{r}</div>
								{/if}
							</div>
							<Button variant="danger" size="sm" onclick={() => removeRole(r)} testId="remove-role-btn">Remove</Button>
						</li>
					{/each}
				</ul>
			{/if}
		{:else}
			<div class="divide-y divide-border">
				{#each Array(3) as _}
					<div class="flex items-center justify-between py-2">
						<div class="space-y-1">
							<div class="h-4 bg-border/60 animate-pulse rounded w-32"></div>
							<div class="h-3 bg-border/60 animate-pulse rounded w-20"></div>
						</div>
						<div class="h-7 bg-border/60 animate-pulse rounded w-16"></div>
					</div>
				{/each}
			</div>
		{/if}
		<div class="mt-3 pt-3 border-t border-border flex justify-end">
			<button class="px-4 py-2 rounded-md font-semibold bg-accent text-[#1a1425] hover:opacity-90 transition-all text-sm" bind:this={addRoleBtnEl} data-testid="add-role-btn">Add Role</button>
		</div>
	</Card>

	<!-- Global Admin Users -->
	<Card title="Global admin users">
		{#if doc}
			{#if doc.global_user_ids.length === 0}
				<div class="text-muted text-sm py-2" data-testid="users-empty">No global admins configured.</div>
			{:else}
				<ul class="divide-y divide-border" data-testid="users-list">
					{#each doc.global_user_ids as u (u)}
						<li class="flex items-center gap-3 py-2">
							<Avatar
								name={doc.names[u] || u}
								userId={u}
								discordAvatar={doc.avatars[u] || null}
								size="sm"
							/>
							<div class="min-w-0 flex-1">
								{#if doc.names[u]}
									<div class="text-sm font-medium">{doc.names[u]}</div>
								{/if}
								<div class="text-xs text-muted font-mono">#{u}</div>
							</div>
							<Button variant="danger" size="sm" onclick={() => removeUser(u)} testId="remove-user-btn">Remove</Button>
						</li>
					{/each}
				</ul>
			{/if}
		{:else}
			<div class="divide-y divide-border">
				{#each Array(2) as _}
					<div class="flex items-center gap-3 py-2">
						<div class="w-6 h-6 rounded-full bg-border/60 animate-pulse"></div>
						<div class="space-y-1">
							<div class="h-4 bg-border/60 animate-pulse rounded w-24"></div>
							<div class="h-3 bg-border/60 animate-pulse rounded w-20"></div>
						</div>
						<div class="flex-1"></div>
						<div class="h-7 bg-border/60 animate-pulse rounded w-16"></div>
					</div>
				{/each}
			</div>
		{/if}
		<div class="mt-3 pt-3 border-t border-border flex justify-end">
			<button class="px-4 py-2 rounded-md font-semibold bg-accent text-[#1a1425] hover:opacity-90 transition-all text-sm" bind:this={addUserBtnEl} data-testid="add-user-btn">Add User</button>
		</div>
	</Card>
</div>

<!-- Add User Modal -->
<Modal bind:open={showAddUser} title="Add global admin" size="sm">
	<FormField label="Discord user ID">
		<Input bind:value={newUserInput} type="text" placeholder="User ID (e.g. 123456789012345678)" />
	</FormField>
	{#snippet footer()}
		<Button variant="secondary" onclick={() => showAddUser = false}>Cancel</Button>
		<Button variant="primary" onclick={handleAddUser} loading={addingUser} disabled={!newUserInput.trim()} testId="add-user-confirm">Add</Button>
	{/snippet}
</Modal>

<!-- Add Role Modal -->
<Modal bind:open={showAddRole} title="Add guild admin role" size="sm">
	<FormField label="Discord role ID">
		<Input bind:value={newRoleInput} type="text" placeholder="Role ID (e.g. 123456789012345678)" />
	</FormField>
	{#snippet footer()}
		<Button variant="secondary" onclick={() => showAddRole = false}>Cancel</Button>
		<Button variant="primary" onclick={handleAddRole} loading={addingRole} disabled={!newRoleInput.trim()} testId="add-role-confirm">Add</Button>
	{/snippet}
</Modal>
