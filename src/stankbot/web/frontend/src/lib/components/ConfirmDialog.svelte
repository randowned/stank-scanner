<script lang="ts">
	import Modal from './Modal.svelte';
	import Button from './Button.svelte';

	interface Props {
		open: boolean;
		title: string;
		body?: string;
		confirmLabel?: string;
		cancelLabel?: string;
		danger?: boolean;
		onconfirm?: () => void | Promise<void>;
		oncancel?: () => void;
	}

	let {
		open = $bindable(),
		title,
		body,
		confirmLabel = 'Confirm',
		cancelLabel = 'Cancel',
		danger = false,
		onconfirm,
		oncancel
	}: Props = $props();

	let busy = $state(false);

	async function confirm() {
		if (busy) return;
		busy = true;
		try {
			await onconfirm?.();
			open = false;
		} finally {
			busy = false;
		}
	}

	function cancel() {
		open = false;
		oncancel?.();
	}
</script>

<Modal bind:open {title} size="sm" onclose={cancel}>
	{#if body}
		<p class="text-sm text-muted">{body}</p>
	{/if}

	{#snippet footer()}
		<Button variant="ghost" onclick={cancel} disabled={busy}>{cancelLabel}</Button>
		<Button variant={danger ? 'danger' : 'primary'} onclick={confirm} loading={busy}>
			{confirmLabel}
		</Button>
	{/snippet}
</Modal>
