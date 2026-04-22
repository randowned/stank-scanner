import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		proxy: {
			'/v2': {
				target: 'http://localhost:8000',
				changeOrigin: true
			}
		}
	},
	kit: {
		alias: {
			$lib: './src/lib'
		}
	}
});