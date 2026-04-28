<script lang="ts">
	import { connectionStatus, onlineUsers } from '$lib/stores';
	import { formatDuration } from '$lib/format';
	import { tick } from 'svelte';

	let open = $state(false);
	let rootEl: HTMLDivElement;
	let btn: HTMLButtonElement;

	const color = $derived(
		$connectionStatus === 'connected'
			? 'bg-ok'
			: $connectionStatus === 'connecting'
				? 'bg-muted'
				: 'bg-danger'
	);
	const pulse = $derived($connectionStatus === 'connected' ? 'animate-pulse' : '');
	const count = $derived($onlineUsers.length);

	$effect(() => {
		tick().then(() => {
			if (!btn || !rootEl) return;
			const handler = (e: MouseEvent) => {
				if (!rootEl.contains(e.target as Node)) open = false;
			};
			const toggle = () => { open = !open; };
			btn.addEventListener('click', toggle);
			document.addEventListener('click', handler);
		});
	});
</script>

<div bind:this={rootEl} class="relative inline-flex items-center">
	<button
		type="button"
		bind:this={btn}
		title="{count} user{count === 1 ? '' : 's'} online"
		aria-label="Online users"
		aria-haspopup="true"
		aria-expanded={open}
		class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors text-muted hover:text-text hover:bg-border/40"
		data-testid="online-badge"
	>
		<span class="w-2 h-2 rounded-full {color} {pulse}" data-testid="online-badge-dot"></span>
		<span data-testid="online-badge-count">{count} online</span>
	</button>

	<div
		role="menu"
		class="absolute top-full right-0 mt-2 z-50 w-64 bg-panel border border-border rounded-lg shadow-xl text-sm text-text"
		class:hidden={!open}
		data-testid="online-popover"
	>
		<div class="px-3 py-2 border-b border-border text-xs font-semibold text-muted uppercase tracking-wide">
			Online Users
		</div>
		<div class="max-h-64 overflow-y-auto">
			{#each $onlineUsers as user (user.user_id)}
				<div class="flex items-center gap-2 px-3 py-2" data-testid="online-user-row">
					<img
						src={user.avatar_url || ''}
						alt={user.username}
						class="w-6 h-6 rounded-full object-cover shrink-0"
						onerror={(e) => {
							const t = e.target as HTMLImageElement;
							t.style.display = 'none';
							if (t.nextElementSibling) (t.nextElementSibling as HTMLElement).style.display = 'flex';
						}}
					/>
					<div
						class="w-6 h-6 rounded-full bg-accent/30 text-text flex items-center justify-center text-xs font-semibold shrink-0"
						style={user.avatar_url ? 'display: none' : ''}
					>
						{user.username.charAt(0).toUpperCase()}
					</div>
					<span class="flex-1 min-w-0 truncate">{user.username}</span>
					<span class="shrink-0 text-xs text-muted tabular-nums">{formatDuration(user.connected_at)}</span>
				</div>
			{/each}
		</div>
	</div>
</div>
