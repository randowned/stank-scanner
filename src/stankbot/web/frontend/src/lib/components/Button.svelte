<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
		size?: 'sm' | 'md' | 'lg';
		type?: 'button' | 'submit' | 'reset';
		href?: string;
		disabled?: boolean;
		loading?: boolean;
		fullWidth?: boolean;
		title?: string;
		onclick?: (e: MouseEvent) => void;
		children?: Snippet;
		class?: string;
		testId?: string;
	}

	let {
		variant = 'primary',
		size = 'md',
		type = 'button',
		href,
		disabled = false,
		loading = false,
		fullWidth = false,
		title,
		onclick,
		children,
		class: klass = '',
		testId
	}: Props = $props();

	const sizeCls: Record<string, string> = {
		sm: 'px-3 py-1 text-sm',
		md: 'px-4 py-2',
		lg: 'px-5 py-3 text-lg'
	};

	const variantCls: Record<string, string> = {
		primary: 'bg-accent text-[#1a1425] hover:opacity-90',
		secondary: 'bg-border text-text hover:bg-border/80',
		danger: 'bg-danger text-white hover:opacity-90',
		ghost: 'bg-transparent text-text hover:bg-border/50'
	};

	const base =
		'inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed';
	const full = $derived(fullWidth ? 'w-full' : '');
	const cls = $derived(`${base} ${sizeCls[size]} ${variantCls[variant]} ${full} ${klass}`.trim());
</script>

{#if href}
	<a {href} {title} class={cls} role="button" aria-disabled={disabled || loading} data-testid={testId}>
		{#if loading}<span class="animate-spin">⟳</span>{/if}
		{@render children?.()}
	</a>
{:else}
	<button {type} {title} class={cls} disabled={disabled || loading} {onclick} data-testid={testId}>
		{#if loading}<span class="animate-spin">⟳</span>{/if}
		{@render children?.()}
	</button>
{/if}
