<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { apiPost } from '$lib/api';
	import { toErrorMessage } from '$lib/api-utils';
	import type { User, GuildInfo } from '$lib/types';
	import Avatar from './Avatar.svelte';
	import Dropdown from './Dropdown.svelte';
	import DropdownItem from './DropdownItem.svelte';
	import GuildSwitcher from './GuildSwitcher.svelte';

	interface Props {
		user: User;
		guilds: GuildInfo[];
		activeGuildId: string | null;
		isAdmin: boolean;
		onerror?: (msg: string) => void;
	}

	let { user, guilds, activeGuildId, isAdmin, onerror }: Props = $props();

	let open = $state(false);
	let guildSwitcherOpen = $state(false);
	let switchingTo: string | null = $state(null);

	const switchable = $derived(guilds);
	const currentPath = $derived($page.url.pathname);
	const isActive = (href: string) => currentPath === href;

	async function switchGuild(guildId: string) {
		if (switchingTo || guildId === activeGuildId) {
			open = false;
			return;
		}
		switchingTo = guildId;
		try {
			await apiPost(`/api/admin/guild?guild_id=${guildId}`);
			window.location.assign(`${base}/`);
		} catch (err) {
			onerror?.(toErrorMessage(err, 'Failed to switch guild'));
			switchingTo = null;
		}
	}

	function toggleGuildSwitcher(e: MouseEvent) {
		e.stopPropagation();
		guildSwitcherOpen = !guildSwitcherOpen;
	}
</script>

<Dropdown bind:open align="right" onclose={() => (guildSwitcherOpen = false)}>
	{#snippet trigger({ toggle, open: isOpen })}
		<button
			type="button"
			onclick={toggle}
			class="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-border/50 transition-colors"
			aria-haspopup="menu"
			aria-expanded={isOpen}
			data-testid="user-menu-trigger"
		>
			<Avatar name={user.username} userId={user.id} discordAvatar={user.avatar} size="sm" />
			<span class="text-sm text-text hidden sm:inline">{user.username}</span>
			<svg
				class="w-3 h-3 text-muted transition-transform {isOpen ? 'rotate-180' : ''}"
				viewBox="0 0 12 12"
				fill="currentColor"
				aria-hidden="true"
			>
				<path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.5" fill="none" />
			</svg>
		</button>
	{/snippet}

	<div class="px-3 py-2 border-b border-border">
		<div class="font-semibold truncate">{user.username}</div>
		<div class="text-xs text-muted truncate">ID {user.id}</div>
	</div>

	<div class="px-3 pt-2 pb-1 text-xs text-muted uppercase tracking-wide">Navigate</div>
	<DropdownItem href="{base}/" active={isActive(base + '/')}>
		<span>🏠</span>
		<span>Dashboard</span>
	</DropdownItem>
	<DropdownItem href="{base}/sessions" active={isActive(base + '/sessions')}>
		<span>📜</span>
		<span>Sessions</span>
	</DropdownItem>
	<DropdownItem href="{base}/media" active={isActive(base + '/media')}>
		<span>📊</span>
		<span>Media</span>
	</DropdownItem>
	<DropdownItem
		href="{base}/player/{user.id}"
		active={isActive(`${base}/player/${user.id}`)}
	>
		<span>👤</span>
		<span>My Profile</span>
	</DropdownItem>

	{#if switchable.length > 1}
		<GuildSwitcher
			guilds={switchable}
			{activeGuildId}
			{switchingTo}
			onswitch={switchGuild}
			ontoggle={toggleGuildSwitcher}
			open={guildSwitcherOpen}
		/>
	{/if}

	{#if isAdmin}
		<div class="border-t border-border my-1"></div>
		<DropdownItem href="{base}/admin" active={currentPath.startsWith(base + '/admin')}>
			<span>⚙️</span>
			<span>Admin</span>
		</DropdownItem>
	{/if}

	<div class="border-t border-border my-1"></div>
	<DropdownItem href="/auth/logout" danger>
		<span>🚪</span>
		<span>Logout</span>
	</DropdownItem>
</Dropdown>
