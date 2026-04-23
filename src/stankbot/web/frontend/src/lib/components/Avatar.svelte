<script lang="ts">
	interface Props {
		src?: string | null;
		name: string;
		size?: 'sm' | 'md' | 'lg';
		userId?: string | null;
		discordAvatar?: string | null;
	}

	let { src, name, size = 'md', userId, discordAvatar }: Props = $props();

	const sizeClasses = {
		sm: 'w-6 h-6 text-xs',
		md: 'w-8 h-8 text-sm',
		lg: 'w-12 h-12 text-base'
	};

	const resolved = $derived.by(() => {
		if (src) return src;
		if (userId && discordAvatar) {
			const ext = discordAvatar.startsWith('a_') ? 'gif' : 'png';
			return `https://cdn.discordapp.com/avatars/${userId}/${discordAvatar}.${ext}`;
		}
		return null;
	});

	const initial = $derived((name || '?').charAt(0).toUpperCase());
</script>

{#if resolved}
	<img
		src={resolved}
		alt={name}
		class="rounded-full object-cover {sizeClasses[size]}"
		referrerpolicy="no-referrer"
	/>
{:else}
	<div
		class="rounded-full bg-accent/30 text-text flex items-center justify-center font-semibold {sizeClasses[size]}"
		aria-label={name}
	>
		{initial}
	</div>
{/if}
