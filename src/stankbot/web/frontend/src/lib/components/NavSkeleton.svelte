<script lang="ts">
	interface Props {
		pattern?: 'dashboard' | 'media' | 'media_detail' | 'admin' | 'generic';
	}

	let { pattern = 'dashboard' }: Props = $props();
</script>

{#if pattern === 'admin'}
	<div class="flex gap-0 min-h-[calc(100vh-57px)]">
		<div class="w-56 shrink-0 bg-panel border-r border-border hidden md:block p-4 space-y-2">
			{#each Array(7) as _}
				<div class="h-9 bg-border/60 animate-pulse rounded-md"></div>
			{/each}
		</div>
		<div class="flex-1 p-4 md:p-6 space-y-4">
			<div class="flex items-center gap-2 mb-4">
				<div class="h-6 bg-border/60 animate-pulse rounded w-8"></div>
				<div>
					<div class="h-5 bg-border/60 animate-pulse rounded w-28 mb-1"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded w-44"></div>
				</div>
			</div>
			<div class="panel">
				<div class="space-y-3">
					{#each Array(6) as _}
						<div class="h-5 bg-border/60 animate-pulse rounded w-full"></div>
					{/each}
				</div>
			</div>
		</div>
	</div>
{:else if pattern === 'media'}
	<div class="p-4 flex flex-col gap-4 max-w-3xl mx-auto">
		<div class="flex items-center gap-2">
			<div class="h-5 bg-border/60 animate-pulse rounded w-16"></div>
		</div>
		<div class="panel">
			<div class="h-5 bg-border/60 animate-pulse rounded w-28 mb-4"></div>
			<div class="flex items-center gap-2">
				<div class="h-8 bg-border/60 animate-pulse rounded w-20"></div>
				<div class="h-8 bg-border/60 animate-pulse rounded w-24"></div>
				<div class="h-8 bg-border/60 animate-pulse rounded w-24 ml-auto"></div>
			</div>
		</div>
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each Array(6) as _}
				<div class="panel overflow-hidden p-0">
					<div class="w-full aspect-video bg-border/60 animate-pulse"></div>
					<div class="p-3 space-y-2">
						<div class="h-4 bg-border/60 animate-pulse rounded w-3/4"></div>
						<div class="h-3 bg-border/60 animate-pulse rounded w-1/2"></div>
						<div class="h-3 bg-border/60 animate-pulse rounded w-1/3"></div>
					</div>
				</div>
			{/each}
		</div>
	</div>
{:else if pattern === 'media_detail'}
	<div class="p-4 flex flex-col gap-4 max-w-3xl mx-auto">
		<div class="flex items-center justify-between">
			<div class="h-4 bg-border/60 animate-pulse rounded w-20"></div>
			<div class="flex gap-2">
				<div class="h-5 bg-border/60 animate-pulse rounded-full w-20"></div>
				<div class="h-5 bg-border/60 animate-pulse rounded w-32"></div>
			</div>
		</div>
		<div class="h-6 bg-border/60 animate-pulse rounded w-64"></div>
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			<div class="md:col-span-1">
				<div class="panel overflow-hidden p-0">
					<div class="w-full aspect-video bg-border/60 animate-pulse"></div>
				</div>
				<div class="mt-3 space-y-2">
					<div class="h-3 bg-border/60 animate-pulse rounded w-28"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded w-24"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded w-20"></div>
				</div>
			</div>
			<div class="md:col-span-2">
				<div class="grid grid-cols-3 gap-3 mb-4">
					{#each Array(3) as _}
						<div class="panel h-20 bg-border/60 animate-pulse"></div>
					{/each}
				</div>
				<div class="panel h-64 bg-border/60 animate-pulse"></div>
			</div>
		</div>
	</div>
{:else if pattern === 'generic'}
	<div class="p-4 flex flex-col gap-4 max-w-3xl mx-auto">
		<div class="panel space-y-3">
			<div class="h-5 bg-border/60 animate-pulse rounded w-32"></div>
			{#each Array(6) as _}
				<div class="h-4 bg-border/60 animate-pulse rounded w-full"></div>
			{/each}
		</div>
	</div>
{:else}
	<div class="p-4 flex flex-col gap-4 max-w-3xl mx-auto">
		<div class="panel">
			<div class="flex items-center gap-2 mb-4">
				<div class="w-6 h-6 bg-border/60 animate-pulse rounded-full"></div>
				<div class="h-5 bg-border/60 animate-pulse rounded w-32"></div>
			</div>
			<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
				<div class="text-center">
					<div class="h-7 bg-border/60 animate-pulse rounded mx-auto w-16 mb-1"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded mx-auto w-20"></div>
				</div>
				<div class="text-center">
					<div class="h-7 bg-border/60 animate-pulse rounded mx-auto w-16 mb-1"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded mx-auto w-20"></div>
				</div>
				<div class="text-center">
					<div class="h-7 bg-border/60 animate-pulse rounded mx-auto w-16 mb-1"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded mx-auto w-20"></div>
				</div>
				<div class="text-center">
					<div class="h-7 bg-border/60 animate-pulse rounded mx-auto w-16 mb-1"></div>
					<div class="h-3 bg-border/60 animate-pulse rounded mx-auto w-20"></div>
				</div>
			</div>
		</div>

		<div class="grid grid-cols-2 gap-4">
			<div class="panel">
				<div class="h-3 bg-border/60 animate-pulse rounded w-16 mb-3 mx-auto"></div>
				<div class="h-4 bg-border/60 animate-pulse rounded w-24 mx-auto mb-2"></div>
				<div class="h-3 bg-border/60 animate-pulse rounded w-12 mx-auto"></div>
			</div>
			<div class="panel">
				<div class="h-3 bg-border/60 animate-pulse rounded w-16 mb-3 mx-auto"></div>
				<div class="h-4 bg-border/60 animate-pulse rounded w-24 mx-auto mb-2"></div>
				<div class="h-3 bg-border/60 animate-pulse rounded w-12 mx-auto"></div>
			</div>
		</div>

		<div class="panel">
			<div class="flex items-center justify-between mb-3">
				<div class="h-5 bg-border/60 animate-pulse rounded w-24"></div>
			</div>
			<div class="space-y-3">
				{#each Array(5) as _}
					<div class="flex items-center gap-3">
						<div class="w-8 h-8 bg-border/60 animate-pulse rounded-full shrink-0"></div>
						<div class="flex-1">
							<div class="h-4 bg-border/60 animate-pulse rounded w-24 mb-2"></div>
							<div class="h-3 bg-border/60 animate-pulse rounded w-16"></div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}
