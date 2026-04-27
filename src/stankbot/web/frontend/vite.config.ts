import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	build: {
		rollupOptions: {
			output: {
				manualChunks(id: string) {
					if (id.includes('node_modules')) {
						return 'vendor';
					}
					if (id.includes('src')) {
						return 'app';
					}
				}
			}
		}
	},
	server: {
		port: 5173,
		proxy: {
			'^/api': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'^/ws': {
				target: 'http://localhost:8000',
				changeOrigin: true,
				ws: true
			},
			'^/auth': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'^/ping': {
				target: 'http://localhost:8000',
				changeOrigin: true
			}
		}
	}
});
