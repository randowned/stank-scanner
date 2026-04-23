import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
	resolve: {
		alias: [
			{ find: '$app/paths', replacement: path.resolve(__dirname, 'src/__mocks__/app-paths.ts') },
			{ find: '$app/environment', replacement: path.resolve(__dirname, 'src/__mocks__/app-environment.ts') },
			// Specific store subpaths before the catch-all mock
			{ find: '$lib/stores/loading', replacement: path.resolve(__dirname, 'src/lib/stores/loading.ts') },
			{ find: '$lib/stores', replacement: path.resolve(__dirname, 'src/__mocks__/stores.ts') },
			{ find: '$lib', replacement: path.resolve(__dirname, 'src/lib') },
			{ find: '$components', replacement: path.resolve(__dirname, 'src/lib/components') }
		]
	},
	test: {
		include: ['src/**/*.test.ts', 'src/**/*.spec.ts'],
		environment: 'jsdom',
		globals: true
	}
});
