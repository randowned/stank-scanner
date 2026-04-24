import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	testDir: './e2e',
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	workers: process.env.CI ? 1 : undefined,
	reporter: 'html',

	projects: [
		{
			name: 'e2e',
			use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:8000' }
		},
		{
			name: 'e2e:dev',
			use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:5173' }
		}
	],

	webServer: [
		{
			command: 'cd ../../../.. && python -m stankbot',
			url: 'http://localhost:8000/healthz',
			reuseExistingServer: !process.env.CI,
			timeout: 30000,
			env: { ENV: 'dev-mock', PYTHONPATH: 'src' } // dev-mock required for mock-login fixtures
		},
		// For e2e:dev project, also start Vite dev server.
		// Health check uses /@vite/client because the auth guard in +layout.ts
		// redirects unauthenticated requests on / to /auth/login (303).
		{
			command: 'npm run dev',
			url: 'http://localhost:5173/@vite/client',
			reuseExistingServer: !process.env.CI,
			timeout: 30000
		}
	]
});
